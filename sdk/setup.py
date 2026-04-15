from setuptools import setup, find_packages

setup(
    name="shield-sdk",
    version="0.1.0",
    description="Python SDK for the Shield AI rights management gateway",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "requests>=2.31.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.23.0",
            "httpx>=0.27.0",
        ]
    },
)
