# boot.py
# Allow CircuitPython code to write to the filesystem (notes, themes, etc.)
# disable_concurrent_write_protection keeps the CIRCUITPY USB drive writable
# from the host PC at the same time.

import board
import storage

# Rotate the built-in display so the REPL/boot text appears in portrait
# (must match the rotation used in code.py)
display = board.DISPLAY
display.rotation = 90

storage.remount("/", readonly=False, disable_concurrent_write_protection=True)
print("boot.py: filesystem remounted read-write")
