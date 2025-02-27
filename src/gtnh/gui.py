import logging
import os
import tkinter as tk
from pathlib import Path
from shutil import copy, rmtree
from tkinter.messagebox import showerror, showinfo, showwarning
from tkinter.ttk import Progressbar
from typing import Any, Callable, List, Optional, Tuple
from zipfile import ZipFile

import requests
from github import Github
from github.Organization import Organization

from gtnh.add_mod import get_repo, new_mod_from_repo
from gtnh.exceptions import LatestReleaseNotFound, PackingInterruptException, RepoNotFoundException
from gtnh.mod_info import GTNHModpack
from gtnh.pack_downloader import download_mod, ensure_cache_dir
from gtnh.utils import get_latest_release, get_token, load_gtnh_manifest, sort_and_write_modpack

log = logging.getLogger("gui")
log.setLevel(logging.WARNING)


def download_mods(
    gtnh_modpack: GTNHModpack,
    github: Github,
    organization: Organization,
    callback: Optional[Callable[[float, str], None]] = None,
) -> Tuple[List[Path], List[Path]]:
    """
    method to download all the mods required for the pack.

    :param gtnh_modpack: GTNHModpack object. Represents the metadata of the modpack.
    :param github: Github object.
    :param organization: Organization object. Represent the GTNH organization.
    :param callback: Callable that takes a float and a string in parameters. (mainly the method to update the
                progress bar that takes a progress step per call and the label used to display infos to the user)
    :return: a list holding all the paths to the clientside mods and a list holding all the paths to the serverside
            mod.
    """
    # computation of the progress per mod for the progressbar
    delta_progress = 100 / len(gtnh_modpack.github_mods)

    # lists holding the paths to the mods
    client_paths = []
    server_paths = []

    # download of the mods
    for mod in gtnh_modpack.github_mods:
        if callback is not None:
            callback(delta_progress, f"downloading mods. current mod: {mod.name} Progress: {{0}}%")

        # do the actual work
        paths = download_mod(github, organization, mod)
        if mod.side == "BOTH":
            client_paths.extend(paths)
            server_paths.extend(paths)
        elif mod.side == "CLIENT":
            client_paths.extend(paths)
        elif mod.side == "SERVER":
            server_paths.extend(paths)

    # todo: make a similar thing for the curse mods

    return client_paths, server_paths


def pack_clientpack(client_paths: List[Path], pack_version: str, callback: Optional[Callable[[float, str], None]] = None) -> None:
    """
    Method used to pack all the client files into a client archive.

    :param client_paths: a list containing all the Path objects refering to the files needed client side.
    :param pack_version: the version of the pack.
    :param callback: Callable that takes a float and a string in parameters. (mainly the method to update the
            progress bar that takes a progress step per call and the label used to display infos to the user)
    :return: None
    """

    # computation of the progress per mod for the progressbar
    delta_progress = 100 / len(client_paths)

    # remembering the cwd because it'll be changed during the zip operation
    cwd = os.getcwd()
    cache_dir = Path(ensure_cache_dir())
    os.chdir(cache_dir)

    # archive name
    archive_name = f"client-{pack_version}.zip"

    # deleting any previous client archive
    if os.path.exists(archive_name):
        os.remove(archive_name)
        log.info("previous client archive deleted")

    log.info("zipping client archive")
    # zipping the files in the archive
    with ZipFile(archive_name, "w") as client_archive:
        for mod_path in client_paths:
            if callback is not None:
                callback(delta_progress, f"Packing client archive version {pack_version}: {mod_path.name}. Progress: {{0}}%")

            # writing the file in the zip
            client_archive.write(mod_path, mod_path.relative_to(cache_dir / "client_archive"))

    log.info("success!")

    # restoring the cwd
    os.chdir(cwd)


def pack_serverpack(server_paths: List[Path], pack_version: str, callback: Optional[Callable[[float, str], None]] = None) -> None:
    """
    Method used to pack all the server files into a client archive.

    :param server_paths: a list containing all the Path objects refering to the files needed server side.
    :param pack_version: the version of the pack.
    :param callback: Callable that takes a float and a string in parameters. (mainly the method to update the
            progress bar that takes a progress step per call and the label used to display infos to the user)
    :return: None
    """

    # computation of the progress per mod for the progressbar
    delta_progress = 100 / len(server_paths)

    # remembering the cwd because it'll be changed during the zip operation
    cwd = os.getcwd()
    cache_dir = Path(ensure_cache_dir())
    os.chdir(cache_dir)

    # archive name
    archive_name = f"server-{pack_version}.zip"

    # deleting any previous client archive
    if os.path.exists(archive_name):
        os.remove(archive_name)
        log.info("previous server archive deleted")

    log.info("zipping client archive")
    # zipping the files in the archive
    with ZipFile(archive_name, "w") as server_archive:
        for mod_path in server_paths:
            if callback is not None:
                callback(delta_progress, f"Packing server archive version {pack_version}: {mod_path.name}. Progress: {{0}}%")

            # writing the file in the zip
            server_archive.write(mod_path, mod_path.relative_to(cache_dir / "server_archive"))

    log.info("success!")

    # restoring the cwd
    os.chdir(cwd)


def download_pack_archive() -> Path:
    """
    Method used to download the latest gtnh modpack archive.

    :return: the path of the downloaded archive
    """
    gtnh_modpack_repo = get_repo("GT-New-Horizons-Modpack")

    gtnh_archive_release = get_latest_release(gtnh_modpack_repo)
    log.info("***********************************************************")
    log.info(f"Downloading {'GT-New-Horizons-Modpack'}:{gtnh_archive_release.title}")

    if not gtnh_archive_release:
        log.warning(f"*** No release found for {'GT-New-Horizons-Modpack'}:{gtnh_archive_release.title}")
        raise LatestReleaseNotFound

    release_assets = gtnh_archive_release.get_assets()
    for asset in release_assets:
        if not asset.name.endswith(".zip"):
            continue

        log.info(f"Found Release at {asset.browser_download_url}")
        cache_dir = ensure_cache_dir()
        gtnh_archive_path = cache_dir / asset.name

        if os.path.exists(gtnh_archive_path):
            log.info(f"Skipping re-redownload of {asset.name}")
            continue

        log.info(f"Downloading {asset.name} to {gtnh_archive_path}")

        headers = {"Authorization": f"token {get_token()}", "Accept": "application/octet-stream"}

        with requests.get(asset.url, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(gtnh_archive_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        log.info("Download successful")
    return gtnh_archive_path


def move_file_to_folder(path_list: List[Path], source_root: Path, destination_root: Path) -> None:
    """
    Function used to move files from the source folder to the destination folder, while keeping the relative path.

    :param path_list: the list of files to move.
    :param source_root: the root folder of the files to move. It is assumed that path_list has files comming from the
                        same root folder.
    :param destination_root: the root folder for the destination.
    :return: None
    """
    for file in path_list:
        dst = destination_root / file.relative_to(source_root)
        if not dst.parent.is_dir():
            os.makedirs(dst.parent)
        copy(file, dst)


def crawl(path: Path) -> List[Path]:
    """
    Function that will recursively list all the files of a folder.

    :param path: The folder to scan
    :return: The list of all the files contained in that folder
    """
    files = [x for x in path.iterdir() if x.is_file()]
    for folder in [x for x in path.iterdir() if x.is_dir()]:
        files.extend(crawl(folder))
    return files


def move_mods(client_paths: List[Path], server_paths: List[Path]) -> None:
    """
    Method used to move the mods in their correct archive folder after they have been downloaded.

    :param client_paths: the paths for the mods clientside
    :param server_paths: the paths for the mods serverside
    :return: None
    """
    client_folder = Path(__file__).parent / "cache" / "client_archive"
    server_folder = Path(__file__).parent / "cache" / "server_archive"
    source_root = Path(__file__).parent / "cache"

    if client_folder.exists():
        rmtree(client_folder)
        os.makedirs(client_folder)

    if server_folder.exists():
        rmtree(server_folder)
        os.makedirs(server_folder)

    move_file_to_folder(client_paths, source_root, client_folder)
    move_file_to_folder(server_paths, source_root, server_folder)


def handle_pack_extra_files() -> None:
    """
    Method used to handle all the files needed by the pack like the configs or the scripts.

    :return: None
    """

    # download the gtnh modpack archive
    # catch is overkill but we never know
    try:
        gtnh_archive_path = download_pack_archive()
    except LatestReleaseNotFound:
        showerror("release not found", "The gtnh modpack repo has no release. Aborting.")
        raise PackingInterruptException

    # prepare for the temp dir receiving the unzip of the archive
    temp_dir = Path(gtnh_archive_path.parent / "temp")
    if temp_dir.exists():
        rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    # unzip
    with ZipFile(gtnh_archive_path, "r") as zip_ref:
        zip_ref.extractall(temp_dir)
    log.info("unzipped the pack")

    # load gtnh metadata
    gtnh_metadata = load_gtnh_manifest()

    # path for the prepared archives
    client_folder = Path(__file__).parent / "cache" / "client_archive"
    server_folder = Path(__file__).parent / "cache" / "server_archive"

    # exclusion lists
    client_exclusions = [temp_dir / exclusion for exclusion in gtnh_metadata.client_exclusions]
    server_exclusions = [temp_dir / exclusion for exclusion in gtnh_metadata.server_exclusions]

    # listing of all the files for the archive
    availiable_files = set(crawl(temp_dir))
    client_files = list(availiable_files - set(client_exclusions))
    server_files = list(availiable_files - set(server_exclusions))

    # moving the files where they must go
    log.info("moving files for the client archive")
    move_file_to_folder(client_files, temp_dir, client_folder)
    log.info("moving files for the server archive")
    move_file_to_folder(server_files, temp_dir, server_folder)
    log.info("success")


class MainFrame(tk.Tk):
    """
    Main windows of DreamAssemblerXXL. Lets you select what you want to do with it via the buttons. Each button spawns
    a new window allowing you to do the selected task(s).
    """

    def __init__(self) -> None:
        """
        Constructor of the MainFrame class.

        :return: None
        """
        tk.Tk.__init__(self)
        self.title("DreamAssemblerXXL")

        # state control vars
        self.is_new_repo_popup_open = False
        self.is_archive_popup_open = False

        # widgets in the window
        self.btn_add_repo = tk.Button(self, text="add a new repository", command=self.open_new_repo_popup)
        self.btn_update_dep = tk.Button(self, text="update dependencies", command=self.handle_dependencies_update)
        self.btn_download = tk.Button(self, text="build archive", command=self.open_archive_popup)

        # grid manager
        self.btn_add_repo.pack()
        self.btn_update_dep.pack()
        self.btn_download.pack()

        # refs to popup toplevel widgets
        self.repo_popup: Optional[AddRepoPopup] = None
        self.archive_popup: Optional[ArchivePopup] = None

    def open_new_repo_popup(self) -> None:
        """
        Opens a new AddRepoPopup popup window. While this window is still open, the main window can't spawn a new one of
        this type.

        :return: None
        """

        def _unlock_popup(_: Any) -> None:
            """
            Method used to change the state var called is_new_repo_popup_open to False when the popup is closed.

            :param _: Event passed by tkinter that we don't care as we know already on what even this function will be
                      bound
            :return: None
            """
            self.is_new_repo_popup_open = False
            self.repo_popup = None

        # prevent the popup from appearing more than once
        if not self.is_new_repo_popup_open:
            self.is_new_repo_popup_open = True
            self.repo_popup = AddRepoPopup()
            self.repo_popup.bind("<Destroy>", _unlock_popup)

    def handle_dependencies_update(self) -> None:
        """
        Opens a new HandleDepUpdatePopup popup window. While this window is still open, the main window can't spawn a
        new one of this type.

        :return: None
        """
        pass

    def open_archive_popup(self) -> None:
        """
        Opens a new ArchivePopup popup window. While this window is still open, the main window can't spawn a new one of
        this type.

        :return: None
        """

        def _unlock_popup(_: Any) -> None:
            """
            Method used to change the state var called is_archive_popup_open to False when the popup is closed.

            :param _: Event passed by tkinter that we don't care as we know already on what even this function will be
                      bound
            :return: None
            """
            self.is_archive_popup_open = False
            self.archive_popup = None

        # prevent the popup from appearing more than once
        if not self.is_archive_popup_open:
            self.is_archive_popup_open = True
            self.archive_popup = ArchivePopup()
            self.archive_popup.bind("<Destroy>", _unlock_popup)


class AddRepoPopup(tk.Toplevel):
    """
    Window allowing you to manage repositories in the github list contained in DreamAssemblerXXL.
    When adding a new Repository, the following things can happen:
    - Will raise you a tkinter error messagebox when the repository is not found.
    - Will raise you a tkinter warning messagebox when the repository is already added.
    - Will raise you a tkinter info messagebox when the repository is successfully added to the list.
    """

    def __init__(self) -> None:
        """
        Constructor of the AddRepoPopup class.

        :return: None
        """
        tk.Toplevel.__init__(self)

        # widgets in the window
        self.label_name_repo = tk.Label(self, text="Add the new repository below")
        self.stringvar_name_repo = tk.StringVar(self)
        self.entry_name_repo = tk.Entry(self, textvariable=self.stringvar_name_repo, width=30)
        self.btn_validate = tk.Button(self, text="validate", command=self.validate)

        # grid manager
        self.label_name_repo.pack()
        self.entry_name_repo.pack()
        self.btn_validate.pack()

        # state control vars
        self.is_messagebox_open = False

    def validate(self) -> None:
        """
        Method executed when self.btn_validate is pressed by the user.

        :return: None
        """
        # if no messagebox had been opened
        if not self.is_messagebox_open:
            self.is_messagebox_open = True

            # resolving the name from the widget
            name = self.stringvar_name_repo.get()

            # checking the repo on github
            try:
                new_repo = get_repo(name)

            # let the user know that the repository doesn't exist
            except RepoNotFoundException:
                showerror("repository not found", f"the repository {name} was not found on github.")

            else:
                # checking if the repo is already added
                gtnh = load_gtnh_manifest()

                # let the user know that the repository is already added
                if gtnh.get_github_mod(new_repo.name):
                    showwarning("repository already added", f"the repository {name} is already added.")

                # adding the repo
                else:
                    try:
                        new_mod = new_mod_from_repo(new_repo)
                        gtnh.github_mods.append(new_mod)
                        sort_and_write_modpack(gtnh)
                        showinfo("repository added successfully", f"the repo {name} was added successfully!")

                    # let the user know that the repository has no release, therefore it won't be added to the list
                    except LatestReleaseNotFound:
                        showerror("no release availiable on the repository", f"the repository {name} has no release, aborting")

            # releasing the blocking
            self.is_messagebox_open = False


class ArchivePopup(tk.Toplevel):
    """
    Window allowing you to pack the archives for all the supported plateforms.
    """

    def __init__(self) -> None:
        """
        Constructor of the ArchivePopup class.

        :return: None
        """
        tk.Toplevel.__init__(self)

        # widgets on the window
        self.progress_bar = Progressbar(self, orient="horizontal", mode="determinate", length=500)
        self.progress_label = tk.Label(self, text="")
        self.btn_start = tk.Button(self, text="start", command=self.start)

        # grid manager
        self.progress_bar.pack()
        self.progress_label.pack()
        self.btn_start.pack()

    def start(self) -> None:
        """
        Method called when self.btn_start is pressed by the user. It starts the packaging process.

        :return: None
        """
        github = Github(get_token())
        organization = github.get_organization("GTNewHorizons")
        gtnh_modpack = load_gtnh_manifest()
        client_folder = Path(__file__).parent / "cache" / "client_archive"
        server_folder = Path(__file__).parent / "cache" / "server_archive"

        try:
            client_paths, server_paths = self.download_mods_client(gtnh_modpack, github, organization)
            move_mods(client_paths, server_paths)
            handle_pack_extra_files()
            self.pack_clientpack_client(crawl(client_folder), gtnh_modpack.modpack_version)
            self.pack_serverpack_client(crawl(server_folder), gtnh_modpack.modpack_version)
            self.pack_technic()
            self.make_deploader_json()
            self.pack_curse()
        except PackingInterruptException:
            pass

    def _progress_callback(self, delta_progress: float, label: str) -> None:
        # updating the progress bar
        self.progress_bar["value"] += delta_progress
        self.progress_bar["value"] = min(100.0, float(format(self.progress_bar["value"], ".2f")))
        self.progress_label["text"] = label.format(self.progress_bar["value"])
        self.update()

    def download_mods_client(self, gtnh_modpack: GTNHModpack, github: Github, organization: Organization) -> Tuple[List[Path], List[Path]]:
        """
        client version of download_mods.

        :param gtnh_modpack: GTNHModpack object. Represents the metadata of the modpack.
        :param github: Github object.
        :param organization: Organization object. Represent the GTNH organization.
        :return: a list holding all the paths to the clientside mods and a list holding all the paths to the serverside
                mod.
        """
        return download_mods(gtnh_modpack, github, organization, self._progress_callback)

    def pack_clientpack_client(self, client_paths: List[Path], pack_version: str) -> None:
        """
        Client version of pack_clientpack.

        :param client_paths: a list containing all the Path objects refering to the files needed client side.
        :param pack_version: the pack version.
        :return: None
        """
        pack_clientpack(client_paths, pack_version, self._progress_callback)

    def pack_serverpack_client(self, server_paths: List[Path], pack_version: str) -> None:
        """
        Client version of pack_serverpack

        :param server_paths: a list containing all the Path objects refering to the files needed server side.
        :param pack_version: the pack version.
        :return: None
        """
        pack_serverpack(server_paths, pack_version, self._progress_callback)

    def make_deploader_json(self) -> None:
        """
        Method used to update the deploader config for curse archives.

        :return: None
        """
        pass

    def pack_curse(self) -> None:
        """
        Method used to generate the curse client and server archives.

        :return: None
        """
        pass

    def pack_technic(self) -> None:
        """
        Method used to generate all the zips needed for solder to update the pack on technic.

        :return: None
        """
        pass


class HandleDepUpdatePopup(tk.Toplevel):
    """
    Window allowing you to update the dependencies.
    """

    def __init__(self) -> None:
        """
        Constructor of HandleDepUpdatePopup class.
        """
        tk.Toplevel.__init__(self)


if __name__ == "__main__":
    m = MainFrame()
    m.mainloop()
