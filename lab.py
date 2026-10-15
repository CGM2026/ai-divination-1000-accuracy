"""Portable entry point; Python 3.10+, no installation required."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from cardlab.cli import main
if __name__=='__main__':main()
