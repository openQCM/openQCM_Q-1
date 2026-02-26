#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
openQCM Q-1 Application Launcher

This is the main entry point for the openQCM Q-1 application.
Run with: python run.py

This wrapper provides a clean entry point that works both in
development and when packaged with PyInstaller.

For development:
    cd OPENQCM
    python run.py

For module execution:
    cd OPENQCM
    python -m openQCM
"""

from openQCM.app import OPENQCM


if __name__ == '__main__':
    OPENQCM().run()
