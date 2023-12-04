#!/usr/bin/env python3

# ======================================================================= #
#  Copyright (C) 2020 - 2023 Dominik Willner <th33xitus@gmail.com>        #
#                                                                         #
#  This file is part of KIAUH - Klipper Installation And Update Helper    #
#  https://github.com/dw-0/kiauh                                          #
#                                                                         #
#  This file may be distributed under the terms of the GNU GPLv3 license  #
# ======================================================================= #

import os
import shutil
import subprocess
import sys
import time
import socket
from pathlib import Path
from typing import List

from kiauh.utils.input_utils import get_confirm
from kiauh.utils.logger import Logger


def kill(opt_err_msg: str = "") -> None:
    """
    Kills the application |
    :param opt_err_msg: an optional, additional error message
    :return: None
    """

    if opt_err_msg:
        Logger.print_error(opt_err_msg)
    Logger.print_error("A critical error has occured. KIAUH was terminated.")
    sys.exit(1)


def parse_packages_from_file(source_file: Path) -> List[str]:
    """
    Read the package names from bash scripts, when defined like:
    PKGLIST="package1 package2 package3" |
    :param source_file: path of the sourcefile to read from
    :return: A list of package names
    """

    packages = []
    print("Reading dependencies...")
    with open(source_file, "r") as file:
        for line in file:
            line = line.strip()
            if line.startswith("PKGLIST="):
                line = line.replace('"', "")
                line = line.replace("PKGLIST=", "")
                line = line.replace("${PKGLIST}", "")
                packages.extend(line.split())

    return packages


def create_python_venv(target: Path) -> None:
    """
    Create a python 3 virtualenv at the provided target destination |
    :param target: Path where to create the virtualenv at
    :return: None
    """
    Logger.print_status("Set up Python virtual environment ...")
    if not target.exists():
        try:
            command = ["python3", "-m", "venv", f"{target}"]
            result = subprocess.run(command, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0 or result.stderr:
                Logger.print_error(f"{result.stderr}", prefix=False)
                Logger.print_error("Setup of virtualenv failed!")
                return

            Logger.print_ok("Setup of virtualenv successfull!")
        except subprocess.CalledProcessError as e:
            Logger.print_error(f"Error setting up virtualenv:\n{e.output.decode()}")
    else:
        if get_confirm("Virtualenv already exists. Re-create?", default_choice=False):
            try:
                shutil.rmtree(target)
                create_python_venv(target)
            except OSError as e:
                log = f"Error removing existing virtualenv: {e.strerror}"
                Logger.print_error(log, False)
        else:
            Logger.print_info("Skipping re-creation of virtualenv ...")


def update_python_pip(target: Path) -> None:
    """
    Updates pip in the provided target destination |
    :param target: Path of the virtualenv
    :return: None
    """
    Logger.print_status("Updating pip ...")
    try:
        command = [f"{target}/bin/pip", "install", "-U", "pip"]
        result = subprocess.run(command, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0 or result.stderr:
            Logger.print_error(f"{result.stderr}", False)
            Logger.print_error("Updating pip failed!")
            return

        Logger.print_ok("Updating pip successfull!")
    except subprocess.CalledProcessError as e:
        Logger.print_error(f"Error updating pip:\n{e.output.decode()}")


def install_python_requirements(target: Path, requirements: Path) -> None:
    """
    Installs the python packages based on a provided requirements.txt |
    :param target: Path of the virtualenv
    :param requirements: Path to the requirements.txt file
    :return: None
    """
    update_python_pip(target)
    Logger.print_status("Installing Python requirements ...")
    try:
        command = [f"{target}/bin/pip", "install", "-r", f"{requirements}"]
        result = subprocess.run(command, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0 or result.stderr:
            Logger.print_error(f"{result.stderr}", False)
            Logger.print_error("Installing Python requirements failed!")
            return

        Logger.print_ok("Installing Python requirements successfull!")
    except subprocess.CalledProcessError as e:
        log = f"Error installing Python requirements:\n{e.output.decode()}"
        Logger.print_error(log)


def update_system_package_lists(silent: bool, rls_info_change=False) -> None:
    """
    Updates the systems package list |
    :param silent: Log info to the console or not
    :param rls_info_change: Flag for "--allow-releaseinfo-change"
    :return: None
    """
    cache_mtime = 0
    cache_files = ["/var/lib/apt/periodic/update-success-stamp", "/var/lib/apt/lists"]
    for cache_file in cache_files:
        if Path(cache_file).exists():
            cache_mtime = max(cache_mtime, os.path.getmtime(cache_file))

    update_age = int(time.time() - cache_mtime)
    update_interval = 6 * 3600  # 48hrs

    if update_age <= update_interval:
        return

    if not silent:
        Logger.print_status("Updating package list...")

    try:
        command = ["sudo", "apt-get", "update"]
        if rls_info_change:
            command.append("--allow-releaseinfo-change")

        result = subprocess.run(command, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0 or result.stderr:
            Logger.print_error(f"{result.stderr}", False)
            Logger.print_error("Updating system package list failed!")
            return

        Logger.print_ok("System package list updated successfully!")
    except subprocess.CalledProcessError as e:
        kill(f"Error updating system package list:\n{e.stderr.decode()}")


def install_system_packages(packages: List[str]) -> None:
    """
    Installs a list of system packages |
    :param packages: List of system package names
    :return: None
    """
    try:
        command = ["sudo", "apt-get", "install", "-y"]
        for pkg in packages:
            command.append(pkg)
        subprocess.run(command, stderr=subprocess.PIPE, check=True)

        Logger.print_ok("Packages installed successfully.")
    except subprocess.CalledProcessError as e:
        kill(f"Error installing packages:\n{e.stderr.decode()}")


def create_directory(_dir: Path) -> None:
    """
    Helper function for creating a directory or skipping if it already exists |
    :param _dir: the directory to create
    :return: None
    """
    try:
        if not os.path.isdir(_dir):
            os.makedirs(_dir, exist_ok=True)
            Logger.print_ok(f"Created directory: {_dir}")
    except OSError as e:
        Logger.print_error(f"Error creating folder: {e}")
        raise


def mask_system_service(service_name: str) -> None:
    """
    Mask a system service to prevent it from starting |
    :param service_name: name of the service to mask
    :return: None
    """
    try:
        command = ["sudo", "systemctl", "mask", service_name]
        subprocess.run(command, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        log = f"Unable to mask system service {service_name}: {e.stderr.decode()}"
        Logger.print_error(log)
        raise


def check_file_exists(file_path: Path) -> bool:
    """
    Helper function for checking the existence of a file where
    elevated permissions are required |
    :param file_path: the absolute path of the file to check
    :return: True if file exists, otherwise False
    """
    try:
        command = ["sudo", "find", file_path]
        subprocess.check_output(command, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


# this feels hacky and not quite right, but for now it works
# see: https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
def get_ipv4_addr() -> str:
    """
    Helper function that returns the IPv4 of the current machine
    by opening a socket and sending a package to an arbitrary IP. |
    :return: Local IPv4 of the current machine
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(("192.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()
