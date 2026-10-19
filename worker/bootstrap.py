"""Launch a Worker entry point with optional isolated dependency directories.

On this Windows host the bundled NumPy is loadable; the newer copy installed
beside Whisper is not. Import the existing NumPy before adding extra packages.
No certificate checks or operating system security settings are changed.
"""
import argparse
import os
from pathlib import Path
import runpy
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dependency-dir', action='append', default=[])
    parser.add_argument('--entry', default=str(Path(__file__).with_name('main.py')))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    import numpy
    import numpy.linalg
    worker = Path(__file__).resolve().parent
    dependencies = [str(Path(path).resolve()) for path in args.dependency_dir]
    for path in dependencies:
        if not Path(path).is_dir():
            raise RuntimeError('Missing dependency directory: ' + path)
    # Optional, project-local NVIDIA wheels; never alter the system driver/PATH.
    dll_handles = []
    if os.name == 'nt':
        for dependency in dependencies:
            for directory in Path(dependency).glob('nvidia/*/bin'):
                dll_handles.append(os.add_dll_directory(str(directory)))
                os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')
    sys.path[:0] = [str(worker), *dependencies]
    arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
    entry = str(Path(args.entry).resolve())
    sys.argv = [entry, *arguments]
    os.chdir(worker.parent)
    runpy.run_path(entry, run_name='__main__')


if __name__ == '__main__':
    main()
