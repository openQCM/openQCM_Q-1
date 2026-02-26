#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
openQCM Q-1 Module Entry Point

Allows running the application as a module:
    python -m openQCM
"""

from openQCM.app import OPENQCM


if __name__ == '__main__':
    OPENQCM().run()
