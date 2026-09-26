# Module entry point for python -m metalheart

import sys  # Exit with the CLI command status

from metalheart.cli import main  # Run the public command-line interface


if __name__ == "__main__":
    sys.exit(main())

