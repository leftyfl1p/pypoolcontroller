import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pypoolcontroller",
    version="1.0",
    author="leftyfl1p",
    author_email="leftyfl1p@me.com",
    description="A python poolcontroller client",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/leftyfl1p/pypoolcontroller",
    packages=setuptools.find_packages(),
    install_requires=['aiohttp>=3.5.4', 'async_timeout>=3.0.1'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)