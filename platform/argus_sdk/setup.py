"""
ARGUS SDK — setup.py

Install with:
    pip install argus-flood-sdk
    # or from source:
    pip install -e .
"""

from setuptools import setup, find_packages

setup(
    name="argus-flood-sdk",
    version="3.0.0",
    description="ARGUS SDK — Deploy AI flood early warning for any river basin",
    long_description=open("README.md").read() if __import__("os").path.exists("README.md") else "",
    long_description_content_type="text/markdown",
    author="ARGUS Foundation",
    author_email="sdk@argus.foundation",
    url="https://github.com/argus-foundation/argus-sdk",
    license="Apache-2.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.27",
        "pyyaml>=6.0",
        "structlog>=24.1",
    ],
    extras_require={
        "ml": [
            "xgboost>=2.0",
            "torch>=2.2",
            "numpy>=1.26",
            "scikit-learn>=1.4",
        ],
        "full": [
            "xgboost>=2.0",
            "torch>=2.2",
            "numpy>=1.26",
            "scikit-learn>=1.4",
            "networkx>=3.2",
            "shapely>=2.0",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Hydrology",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
