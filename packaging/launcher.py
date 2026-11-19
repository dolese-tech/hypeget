"""Entry point for the packaged Windows build (PyInstaller needs a plain script)."""
import multiprocessing

from hypeget.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
