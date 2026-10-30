"""Inspect only a vendor-owned DDE Link produced by the approved market export UI."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path

CLIENT = Path(r"D:\Download\行情分析端\isky.exe")


def parse_link(raw):
    if not isinstance(raw,bytes) or not 3 <= len(raw) <= 8192:
        raise ValueError("DDE_LINK_SIZE: invalid public link size")
    if raw[1:2] == b"\0":
        text = raw.decode("utf-16le",errors="strict")
    else:
        text = raw.decode("gb18030",errors="strict")
    if not text.endswith("\0\0"):
        raise ValueError("DDE_LINK_TERMINATOR: expected a terminated public link")
    fields = text.rstrip("\0").split("\0")
    if len(fields) != 3 or any(not x or len(x)>2048 or any(ord(c)<32 for c in x) for x in fields):
        raise ValueError("DDE_LINK_FIELDS: expected application, topic and item")
    service,topic,item = fields
    if service.casefold() not in ("skyserver","sky2008","sky2020","isky","sky") or topic.casefold()=="system":
        raise ValueError("DDE_DESTINATION: link is not an approved vendor market service")
    return dict(service=service,topic=topic,item=item)


def inspect_vendor_link():
    if os.name != "nt":
        return dict(status="UNSUPPORTED_PLATFORM",content_read=False)
    user = ctypes.WinDLL("user32",use_last_error=True)
    kernel = ctypes.WinDLL("kernel32",use_last_error=True)
    user.GetClipboardOwner.restype = wintypes.HWND
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
    user.RegisterClipboardFormatW.argtypes = (wintypes.LPCWSTR,)
    user.RegisterClipboardFormatW.restype = wintypes.UINT
    user.GetClipboardData.argtypes = (wintypes.UINT,)
    user.GetClipboardData.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.GlobalSize.argtypes = (wintypes.HGLOBAL,)
    kernel.GlobalSize.restype = ctypes.c_size_t
    kernel.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    fmt = user.RegisterClipboardFormatW("Link")
    result = dict(status="OWNER_NOT_VERIFIED",content_read=False,owner_is_client=False,
                  link_format_available=bool(fmt and user.IsClipboardFormatAvailable(fmt)))
    owner = user.GetClipboardOwner()
    if not owner:
        return dict(result,status="NO_CLIPBOARD_OWNER_VISIBLE")
    pid = wintypes.DWORD()
    if not user.GetWindowThreadProcessId(owner,ctypes.byref(pid)) or not pid.value:
        return dict(result,status="OWNER_WINDOW_NOT_VISIBLE")
    handle = kernel.OpenProcess(0x1000,False,pid.value)
    if not handle:
        return dict(result,status="OWNER_QUERY_DENIED",win32_error=ctypes.get_last_error())
    try:
        name = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(name))
        if not kernel.QueryFullProcessImageNameW(handle,0,name,ctypes.byref(size)) or Path(name.value).resolve()!=CLIENT.resolve():
            return result
    finally:
        kernel.CloseHandle(handle)
    result["owner_is_client"] = True
    if not fmt or not user.IsClipboardFormatAvailable(fmt):
        return dict(result,status="NO_VENDOR_DDE_LINK")
    if not user.OpenClipboard(None):
        return dict(result,status="CLIPBOARD_BUSY")
    try:
        if user.GetClipboardOwner()!=owner:
            return dict(result,status="OWNER_CHANGED")
        data = user.GetClipboardData(fmt)
        if not data:
            return dict(result,status="NO_LINK_DATA")
        size = kernel.GlobalSize(data)
        if not 3 <= size <= 8192:
            return dict(result,status="LINK_SIZE_REJECTED")
        pointer = kernel.GlobalLock(data)
        if not pointer:
            return dict(result,status="LINK_LOCK_FAILED")
        try:
            width = 2 if size >= 2 and ctypes.c_ubyte.from_address(pointer+1).value == 0 else 1
            raw, zeros = bytearray(), 0
            for offset in range(0,size-width+1,width):
                part = ctypes.string_at(pointer+offset,width)
                raw.extend(part)
                zeros = zeros+1 if not any(part) else 0
                if zeros == 2:
                    break
            raw = bytes(raw)
        finally:
            kernel.GlobalUnlock(data)
        try:
            link = parse_link(raw)
        except (ValueError,UnicodeError) as exc:
            return dict(result,status="LINK_REJECTED",reason=str(exc),content_read=True)
        return dict(result,status="VENDOR_LINK_INSPECTED",content_read=True,link=link,
                    note="Connection parameters only; no DDE request, execution, account or private process memory access")
    finally:
        user.CloseClipboard()


def probe_market_service():
    result=dict(service='SkyServer',topic='Min1',candidate_only=True,
                data_request_sent=False,execute_sent=False)
    if os.name!='nt':return dict(result,status='UNSUPPORTED_PLATFORM')
    user=ctypes.WinDLL('user32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(ctypes.c_void_p,wintypes.UINT,wintypes.UINT,
                                   ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                                   ctypes.c_size_t,ctypes.c_size_t)
    callback=callback_type(lambda *args:None)
    user.DdeInitializeW.argtypes=(ctypes.POINTER(wintypes.DWORD),callback_type,wintypes.DWORD,wintypes.DWORD)
    user.DdeCreateStringHandleW.argtypes=(wintypes.DWORD,wintypes.LPCWSTR,ctypes.c_int)
    user.DdeCreateStringHandleW.restype=ctypes.c_void_p
    user.DdeConnect.argtypes=(wintypes.DWORD,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p)
    user.DdeConnect.restype=ctypes.c_void_p
    user.DdeGetLastError.argtypes=(wintypes.DWORD,)
    user.DdeDisconnect.argtypes=(ctypes.c_void_p,)
    user.DdeFreeStringHandle.argtypes=(wintypes.DWORD,ctypes.c_void_p)
    user.DdeUninitialize.argtypes=(wintypes.DWORD,)
    instance=wintypes.DWORD()
    error=user.DdeInitializeW(ctypes.byref(instance),callback,0x10,0)
    if error:return dict(result,status='DDE_INITIALIZE_FAILED',error=error)
    service=topic=conversation=None
    try:
        service=user.DdeCreateStringHandleW(instance.value,result['service'],1200)
        topic=user.DdeCreateStringHandleW(instance.value,result['topic'],1200)
        if not service or not topic:return dict(result,status='DDE_NAME_FAILED')
        conversation=user.DdeConnect(instance.value,service,topic,None)
        if not conversation:return dict(result,status='CANDIDATE_NOT_CONNECTED',error=user.DdeGetLastError(instance.value))
        return dict(result,status='CANDIDATE_CONNECTED_NO_DATA',note='Peer and item schema still unverified; no data or execute transaction sent')
    finally:
        if conversation:user.DdeDisconnect(conversation)
        if service:user.DdeFreeStringHandle(instance.value,service)
        if topic:user.DdeFreeStringHandle(instance.value,topic)
        user.DdeUninitialize(instance.value)


def main():
    import argparse
    from datetime import datetime,timezone
    import json
    parser=argparse.ArgumentParser(description="只读探测指定行情端产生的DDE Link；不会读取任意剪贴板或执行DDE命令")
    parser.add_argument("--inspect-link",action="store_true",required=True)
    parser.parse_args()
    result=inspect_vendor_link()
    result['service_probe']=probe_market_service()
    result['checked_at']=datetime.now(timezone.utc).isoformat()
    folder=Path(__file__).resolve().parents[1]/'runtime/dde'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/('inspection-'+datetime.now().strftime('%Y%m%dT%H%M%S%f')+'.json')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('探测记录：'+str(path))
    if not result['content_read']:
        print('未读取剪贴板内容；只有来源已验证为指定行情端且存在Link格式时才会读取公开DDE参数。')


if __name__=='__main__':main()
