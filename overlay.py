import ctypes
import tkinter as tk


def get_dpi_scale() -> float:
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi / 96.0
    except Exception:
        return 1.0


def start_overlay(root: tk.Tk, on_complete):
    """
    Show a fullscreen selection overlay as a Toplevel on the given root.
    on_complete(region) is called with a dict {x, y, w, h} in physical pixels,
    or None if cancelled.
    """
    win = tk.Toplevel(root)
    win.attributes('-fullscreen', True)
    win.attributes('-topmost', True)
    win.configure(bg='black')
    win.attributes('-alpha', 0.2)  # Slight dim overlay; avoids click-through issues
    win.overrideredirect(True)

    canvas = tk.Canvas(win, bg='black', highlightthickness=0, cursor='crosshair')
    canvas.pack(fill='both', expand=True)

    sw = root.winfo_screenwidth()
    canvas.create_text(
        sw // 2, 28,
        text="Drag to select region   |   Escape to cancel",
        fill='cyan', font=('Segoe UI', 13),
    )

    start = {}
    rect_id = [None]

    def on_press(e):
        start['x'] = e.x
        start['y'] = e.y
        if rect_id[0]:
            canvas.delete(rect_id[0])
        rect_id[0] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline='cyan', width=2)

    def on_drag(e):
        if rect_id[0]:
            canvas.coords(rect_id[0], start['x'], start['y'], e.x, e.y)

    def on_release(e):
        x1 = min(start.get('x', e.x), e.x)
        y1 = min(start.get('y', e.y), e.y)
        x2 = max(start.get('x', e.x), e.x)
        y2 = max(start.get('y', e.y), e.y)
        w, h = x2 - x1, y2 - y1
        win.destroy()
        if w > 5 and h > 5:
            scale = get_dpi_scale()
            on_complete({
                'x': int(x1 * scale),
                'y': int(y1 * scale),
                'w': int(w * scale),
                'h': int(h * scale),
            })
        else:
            on_complete(None)

    def on_escape(e):
        win.destroy()
        on_complete(None)

    canvas.bind('<ButtonPress-1>', on_press)
    canvas.bind('<B1-Motion>', on_drag)
    canvas.bind('<ButtonRelease-1>', on_release)
    win.bind('<Escape>', on_escape)
    win.focus_force()
