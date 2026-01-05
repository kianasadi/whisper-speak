from setuptools import setup

def readme():
    with open('README.md') as f:
        return f.read()


with open('README.rst') as f:
    long_description = f.read()

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(name='wkey',
      version='3',
      description='Integrate OpenAI speech-to-text Whisper with your keyboard',
      long_description=long_description,
      long_description_content_type='text/markdown',
      url='',
      author='',
      author_email='',
      license='',
      packages=['wkey'],
      scripts=['scripts/wkey', 'scripts/wkey-gui', 'scripts/fkey'],
      install_requires=required,
      include_package_data=True,
      zip_safe=False
      )
 