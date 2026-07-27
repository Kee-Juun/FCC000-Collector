# acrylic_blur.py
# Windows API blur effect module for frosted glass effect

import ctypes
from ctypes import wintypes

# Win32 structs / constants
ACCENT_DISABLED = 0
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

WCA_ACCENT_POLICY = 19


class ACCENTPOLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),  # AABBGGRR
        ("AnimationId", ctypes.c_int),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def enable_blur(hwnd: int, acrylic: bool = True, opacity: int = 0xCC, tint_color: tuple = (20, 22, 26)) -> bool:
    """
    Enable Windows acrylic/blur effect for frosted glass look.
    
    Args:
        hwnd: Window handle (int)
        acrylic: True -> acrylic blur; False -> blurbehind
        opacity: 0x00..0xFF alpha (higher = less transparent). Default 0xCC (~80%)
        tint_color: RGB tuple for tint color. Default (20, 22, 26) - dark gray
    
    Returns:
        bool: True if blur was successfully enabled, False otherwise
    """
    try:
        user32 = ctypes.windll.user32
        SetWindowCompositionAttribute = user32.SetWindowCompositionAttribute
        SetWindowCompositionAttribute.argtypes = (wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA))
        SetWindowCompositionAttribute.restype = wintypes.BOOL
        
        accent = ACCENTPOLICY()
        accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND if acrylic else ACCENT_ENABLE_BLURBEHIND
        accent.AccentFlags = 2  # often 2 works nicely
        # GradientColor is AABBGGRR. Here we use a dark tint.
        r, g, b = tint_color
        accent.GradientColor = (opacity << 24) | (b << 16) | (g << 8) | r

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.SizeOfData = ctypes.sizeof(accent)
        data.Data = ctypes.addressof(accent)

        result = SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return result != 0  # Returns True on success
    except (AttributeError, OSError, Exception):
        # Not on Windows or API not available
        return False


def is_windows() -> bool:
    """Check if running on Windows."""
    try:
        import platform
        return platform.system() == "Windows"
    except Exception:
        return False


def set_rounded_window_region(hwnd: int, radius: int) -> bool:
    """
    Set a rounded window region using Windows API to clip the window shape.
    This helps the blur backdrop respect rounded corners.
    
    Args:
        hwnd: Window handle (int)
        radius: Corner radius in pixels
    
    Returns:
        bool: True if region was successfully set, False otherwise
    """
    try:
        if not is_windows():
            return False
        
        import ctypes
        from ctypes import wintypes
        
        # Windows API constants
        GWL_STYLE = -16
        WS_POPUP = 0x80000000
        WS_THICKFRAME = 0x00040000
        
        # Get window dimensions
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long),
                       ("top", ctypes.c_long),
                       ("right", ctypes.c_long),
                       ("bottom", ctypes.c_long)]
        
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        
        if width <= 0 or height <= 0:
            return False
        
        # Create rounded region using CreateRoundRectRgn
        # HRGN CreateRoundRectRgn(int x1, int y1, int x2, int y2, int w, int h)
        region = gdi32.CreateRoundRectRgn(0, 0, width, height, radius * 2, radius * 2)
        if region:
            # SetWindowRgn sets the window region
            # int SetWindowRgn(HWND hWnd, HRGN hRgn, BOOL bRedraw)
            result = user32.SetWindowRgn(hwnd, region, 1)  # 1 = TRUE for redraw
            return result != 0
        return False
    except Exception:
        return False

