import sys

from lobster_mvp import startup_smoke_check

sys.exit(0 if startup_smoke_check() else 1)
