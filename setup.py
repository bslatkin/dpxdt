from setuptools import setup, find_packages

setup(name='dpxdt',
      version='0.1.0',
      description='Screenshot diff tool',
      author='Brett Slatkin',
      author_email='brett@haxor.com',
      url='https://github.com/bslatkin/dpxdt/',
      entry_points={
          'console_scripts': [
              'dpxdt = dpxdt.tools.local_pdiff:run',
          ],
      },
      packages=find_packages(exclude=['tests*','dependencies*']),
      install_requires=[
          'PyYAML',
          'python-gflags',
          'poster'
      ],
      include_package_data=True,
      classifiers=[
          'Environment :: Console',
          'Environment :: Web Environment',
          'Framework :: Flask',
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: Apache Software License',
          'Topic :: Software Development :: Version Control'
      ],
)
