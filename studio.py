# Repository entry point for the Metalheart Studio CLI

import sys  # Exit with the CLI command status

from metalheart.cli import main  # Run the package command-line interface


if __name__ == "__main__":
    sys.exit(main())

