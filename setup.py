from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="experiencemd",
    version="0.1.0",
    author="Quantum Agents Project",
    description="Python reference implementation of the experience.md standard — transferable AI agent experience",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/quantum-agents/experience-md",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[],          # zero hard dependencies — stdlib only
    extras_require={
        "yaml":       ["pyyaml>=6.0"],
        "embeddings": ["sentence-transformers>=2.0", "numpy>=1.24"],
        "vector":     ["chromadb>=0.4", "numpy>=1.24"],
        "dev":        ["pytest>=7.0", "pyyaml>=6.0"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords=[
        "ai-agents", "experience-transfer", "agent-memory",
        "quantumity", "llm", "multi-agent", "experience-md"
    ],
)
