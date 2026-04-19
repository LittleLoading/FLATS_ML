import subprocess
import sys
import os


def install_requirements():
    """
        Installs requirements from requirements.txt
    :return:nothing
    """
    requirements = os.path.join(os.path.dirname(__file__), "requirements.txt")

    if not os.path.exists(requirements):
        print("requirements.txt not found!")
        sys.exit(1)

    print("Dependencies installed.\n")


def run_app():
    app = os.path.join(os.path.dirname(__file__), "UI", "app.py")

    if not os.path.exists(app):
        print("app.py not found in UI/!")
        sys.exit(1)

    print("Starting Flats ML")
    subprocess.call([sys.executable, app])


if __name__ == "__main__":
    install_requirements()
    run_app()