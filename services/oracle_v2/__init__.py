"""ORACLE v2 — On-Device MobileFloodFormer (port 8017).

Replaces ORACLE v1 (XGBoost) with a tiny transformer that captures
temporal patterns XGBoost misses: subtle rising-rate signatures
6 hours before floods. Still fits in 500KB on Raspberry Pi 5.
"""
