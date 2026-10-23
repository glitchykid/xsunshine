"""Windows registry traversal and transactional empty-key deletion."""

import ctypes
import os
import uuid
from contextlib import ExitStack, contextmanager
from ctypes import wintypes

from xsunshine.core import Skipped, Snapshot

if os.name == "nt":
    import winreg

HIVES = {
    "HKCU": "HKEY_CURRENT_USER",
    "HKLM": "HKEY_LOCAL_MACHINE",
    "HKU": "HKEY_USERS",
    "HKCR": "HKEY_CLASSES_ROOT",
    "HKCC": "HKEY_CURRENT_CONFIG",
}


@contextmanager
def _owned_key(handle):
    try:
        yield handle
    finally:
        winreg.CloseKey(handle)


def normalize_registry_path(value: str) -> str:
    parts = value.split("\\")
    hive = parts[0].upper()
    hive = next((short for short, full in HIVES.items() if hive == full), hive)
    if hive not in HIVES or "\x00" in value or any(part in ("", ".", "..") for part in parts[1:]):
        raise ValueError("Use a registry path such as HKCU\\Software or HKLM")
    return "\\".join([hive, *parts[1:]])


class RegistryAPI:
    """Small typed bindings for APIs not exposed by winreg."""

    def __init__(self):
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        ktm = ctypes.WinDLL("ktmw32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = wintypes.HANDLE
        dword = wintypes.DWORD
        text = wintypes.LPCWSTR
        pointer = ctypes.c_void_p
        self.open = advapi.RegOpenKeyExW
        self.open.argtypes = [handle, text, dword, dword, ctypes.POINTER(handle)]
        self.open.restype = wintypes.LONG
        self.enlist = advapi.RegOpenKeyTransactedW
        self.enlist.argtypes = [handle, text, dword, dword, ctypes.POINTER(handle), handle, pointer]
        self.enlist.restype = wintypes.LONG
        self.delete = advapi.RegDeleteKeyTransactedW
        self.delete.argtypes = [handle, text, dword, dword, handle, pointer]
        self.delete.restype = wintypes.LONG
        self.create = ktm.CreateTransaction
        self.create.argtypes = [pointer, pointer, dword, dword, dword, dword, text]
        self.create.restype = handle
        self.commit = ktm.CommitTransaction
        self.commit.argtypes = [handle]
        self.commit.restype = wintypes.BOOL
        self.close = kernel.CloseHandle
        self.close.argtypes = [handle]
        self.close.restype = wintypes.BOOL

    @contextmanager
    def transaction(self):
        transaction = self.create(None, None, 0, 0, 0, 5000, "XSunshine empty key cleanup")
        if transaction == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield transaction
        finally:
            # Closing an uncommitted transaction rolls back its changes.
            self.close(transaction)


class RegistryTree:
    def __init__(self, root: str, view: str = "64"):
        if os.name != "nt":
            raise OSError("Registry cleanup requires Windows")
        if view not in ("32", "64"):
            raise ValueError("Registry view must be 32 or 64")
        self.root = normalize_registry_path(root)
        self.view = winreg.KEY_WOW64_64KEY if view == "64" else winreg.KEY_WOW64_32KEY
        self.kind = "registry" + view
        self.api = RegistryAPI()

    def _guard(self, node: str, *, deleting: bool = False) -> str:
        node = normalize_registry_path(node)
        if not (
            node.casefold() == self.root.casefold()
            or node.casefold().startswith(self.root.casefold() + "\\")
        ):
            raise ValueError("Registry key is outside the selected scope")
        if deleting and node.casefold() == self.root.casefold():
            raise ValueError("The selected registry root cannot be removed")
        return node

    @staticmethod
    def _check_link(key):
        try:
            _, kind = winreg.QueryValueEx(key, "SymbolicLinkValue")
        except FileNotFoundError:
            return
        if kind == winreg.REG_LINK:
            raise Skipped("Registry symbolic link")

    def _open_child(self, parent, name):
        handle = wintypes.HANDLE()
        error = self.api.open(
            int(parent), name, 8, winreg.KEY_READ | self.view, ctypes.byref(handle)
        )  # REG_OPTION_OPEN_LINK
        if error:
            raise ctypes.WinError(error)
        return _owned_key(handle.value)

    @contextmanager
    def _open_path(self, node):
        parts = node.split("\\")
        # Open each component without following registry links, including those
        # above an explicitly selected root. Keep handles alive until inspection ends.
        with ExitStack() as handles:
            current = handles.enter_context(
                winreg.OpenKey(getattr(winreg, HIVES[parts[0]]), "", 0, winreg.KEY_READ | self.view)
            )
            for name in parts[1:]:
                current = handles.enter_context(self._open_child(current, name))
                self._check_link(current)
            yield current

    def inspect(self, node: str) -> Snapshot:
        node = self._guard(node)
        with self._open_path(node) as key:
            child_count, value_count, _ = winreg.QueryInfoKey(key)
            children = tuple(node + "\\" + winreg.EnumKey(key, i) for i in range(child_count))
            return Snapshot(tuple(sorted(children)), value_count != 0)

    def remove_empty(self, node: str, identity: object) -> bool:
        node = self._guard(node, deleting=True)
        parent_path, name = node.rsplit("\\", 1)
        with self._open_path(parent_path) as parent, self._open_child(parent, name) as child:
            self._check_link(child)
            with self.api.transaction() as transaction:
                handle = wintypes.HANDLE()
                # Open the named key in the transaction. An empty subkey string
                # only duplicates a handle and does not reliably enlist the key.
                error = self.api.enlist(
                    int(parent),
                    name,
                    0,
                    winreg.KEY_READ | winreg.KEY_SET_VALUE | self.view,
                    ctypes.byref(handle),
                    transaction,
                    None,
                )
                if error:
                    raise ctypes.WinError(error)
                with _owned_key(handle.value) as checked:
                    if any(winreg.QueryInfoKey(checked)[:2]):
                        return False
                    # Acquire the transaction's write lock before the empty check.
                    # The marker is private to the transaction and removed before
                    # committing. A failed operation rolls it back automatically.
                    marker = "XSunshine.Transaction." + uuid.uuid4().hex
                    winreg.SetValueEx(checked, marker, 0, winreg.REG_NONE, b"")
                    winreg.DeleteValue(checked, marker)
                    child_count, value_count, _ = winreg.QueryInfoKey(checked)
                    if child_count or value_count:
                        return False
                    error = self.api.delete(int(parent), name, self.view, 0, transaction, None)
                    if error:
                        raise ctypes.WinError(error)
                    if not self.api.commit(transaction):
                        raise ctypes.WinError(ctypes.get_last_error())
                return True
