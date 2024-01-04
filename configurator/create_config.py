import argparse
import grp
import json
import os
import subprocess
import pwd
import stat
import sys
import uuid

from filelock import FileLock


def generate_project_id():
    return uuid.uuid4().hex


# region paths
def ports_path():
    return f"/srv/pv-configurator/ports.json"


def projects_dir_path():
    return f"/srv/pv-configurator/projects.json"


def project_path(project_id):
    return f"/srv/pv-configurator/projects/{project_id}"


def launcher_config_path(project_id):
    return f"{project_path(project_id)}/launcher_config.json"


def project_config_path(project_id):
    return f"{project_path(project_id)}/config.json"


def sessions_path(project_id):
    return f"/srv/pv-configurator/project-proxies/{project_id}.proxy.txt"


def service_path(project_id):
    return f"{project_path(project_id)}/pv-{project_id}-launcher.service"


def settings_file():
    return f"/srv/pv-configurator/configurator_settings.json"


# endregion

# region config files

def systemd_unit(username, settings, project_id):
    return f"""
    [Unit]
    Description=Paraview Python Launcher for Project {project_id} of User {username}
    After=network.target
    [Service]
    Type=simple
    Restart=no
    ExecStart={settings.launcher_exec} {launcher_config_path(project_id)}
    RestartSec=5
    
    [Service]
    User=pv-launcher
    Group=pv-launcher
    
    [Install]
    WantedBy=multi-user.target
    """


def launcher_config(username, settings, project_id, port, port_ranges, dataDir, loadFile):
    # python_exec = "/usr/local/lib/paraview/bin/pvpython"
    servername = settings.servername
    python_exec = settings.python_exec
    visualizer_exec = settings.visualizer_exec
    # visualizer_exec = "/usr/local/lib/paraview/share/paraview-5.11/web/visualizer/server/pvw-visualizer.py"
    cmd = [
        "sudo", "-u", username,
        python_exec, "--dr", visualizer_exec, "--port", "${port}", "--data", dataDir, "--debug",
        "--authKey", "${secret}"
    ]

    if loadFile:
        cmd.append("--load-file")
        cmd.append(loadFile)

    return {
        "configuration": {
            "host": "localhost",
            "port": port,
            "proxy_file": sessions_path(project_id),
            "endpoint": "visualizer",
            "sessionURL": f"ws://{servername}/ws?project={project_id}&sessionId=${{id}}",
            "fields": ["secret"],
            "timeout": 60,
            "log_dir": f"/var/log/paraview-launcher/{project_id}",
        },

        "properties": {},

        "resources": [
            {"host": "localhost", "port_range": [s, e]} for s, e in port_ranges
        ],

        "apps": {
            "visualizer": {
                "cmd": cmd,
                "ready_line": "Starting factory"
            }
        }
    }


def project_values(port, port_ranges, dataDir, loadFile):
    config = {
        "port": port,
        "port_ranges": [[s, e] for s, e in port_ranges],
        "dataDir": dataDir,
        "loadFile": loadFile
    }
    return config


# endregion

# region ports

def get_free_ports(reserved, n):
    from_port = 9000

    free_ranges = []
    allocated = 0
    for rng in reserved:
        [rf, rt] = rng
        if rf <= from_port:
            from_port = rt + 1
        else:
            # free from from_port (incl) to rf (excl)
            allocate = min(rf - from_port, n - allocated)
            free_ranges.append((from_port, from_port + allocate - 1))
            allocated += allocate
            if allocated == n:
                break
            from_port = rt + 1
            if allocated > n:
                raise "assertion error"

    if allocated < n:
        allocate = n - allocated
        free_ranges.append((from_port, from_port + allocate - 1))
        if from_port + allocate > 20000:
            raise "no free ports available"

    (first_port, range_end) = free_ranges[0]
    if first_port == range_end:
        free_ranges.pop(0)
        return first_port, free_ranges
    else:
        free_ranges[0] = (first_port + 1, range_end)
        return first_port, free_ranges


def release_single_range(reserved, port_range):
    """Does the reverse of reserve_single_range
    """
    (f, t) = port_range
    i = 0
    while i < len(reserved):
        [rf, rt] = reserved[i]
        if f <= rf <= t:
            if rt <= t:
                reserved.pop(i)
                i -= 1
            else:
                reserved[i] = [t + 1, rt]
        elif f <= rt <= t:
            if rf >= f:
                reserved.pop(i)
                i -= 1
            else:
                reserved[i] = [rf, f - 1]
        elif rf <= f <= rt:
            if t >= rt:
                reserved[i] = [rf, f - 1]
            else:
                reserved[i] = [rf, f - 1]
                reserved.insert(i + 1, [t + 1, rt])
                i += 1
        elif rf <= t <= rt:
            if f <= rf:
                reserved[i] = [t + 1, rt]
            else:
                reserved[i] = [rf, f - 1]
                reserved.insert(i + 1, [t + 1, rt])
                i += 1

        i += 1


def reserve_single_range(reserved, port_range):
    """ Add another port range (2-tuple) to reserved (list of 2-element list)

    Takes a list of ranges (in the form of 2-element-lists) which each define a reserved port range.
    The ranges in the list are assumed to be not overlapping and not touching.
    The list itself is assumed to be sorted such that ranges containing larger values come after
    ranges with smaller values
    Inserts the port_range into the list at the correct position and joins it with the ranges before and/or after,
    if possible

    | Example #1:
    | reserved = [[1,3], [10,12]] \n
    | reserve_single_range(reserved, (6,8)) -> reserved == [[1,3], [6,8], [10,12]]

    | Example #2:
    | reserved = [[1,3], [10,12]]
    | reserve_single_range(reserved, (4,8)) -> reserved == [[1,8], [10,12]]

    | Example #3:
    | reserved = [[1,3], [10,12], [15,20]]
    | reserve_single_range(reserved, (4,9)) -> reserved == [[1,12], [15,20]]
    """
    (f, t) = port_range
    tuple_before = None
    before_idx = None
    tuple_after = None
    after_idx = None
    for i in range(0, len(reserved)):
        [rf, rt] = reserved[i]
        # assuming f<=t and rf<=rt

        if rf <= t and f <= rt:
            raise f"cannot reserve range {f}-{t}: overlapping with {rf}-{rt}"
        if rt < f:
            # overwrite until rt > f
            tuple_before = (rf, rt)
            before_idx = i
        if rf > t:
            # take the first where rf > t
            tuple_after = (rf, rt)
            after_idx = i
            break
    if tuple_before is not None and tuple_after is not None:
        bf, bt = tuple_before
        af, at = tuple_after
        if bt == f - 1 and af == t + 1:
            # merge tuple before and after to a single large one
            reserved.pop(after_idx)
            reserved[before_idx] = [bf, at]
        elif bt == f - 1:
            # increase tuple before to the end of the requested range
            reserved[before_idx] = [bf, t]
        elif af == t + 1:
            # increase tuple after backwards to the beginning of the requested range
            reserved[after_idx] = [f, at]
        else:
            reserved.insert(after_idx, [f, t])
    elif tuple_before is not None:
        bf, bt = tuple_before
        if bt == f - 1:
            # increase tuple before to the end of the requested range
            reserved[before_idx] = [bf, t]
        else:
            reserved.append([f, t])
    elif tuple_after is not None:
        af, at = tuple_after
        if af == t + 1:
            # increase tuple after backwards to the beginning of the requested range
            reserved[after_idx] = [f, at]
        else:
            reserved.insert(0, [f, t])
    else:
        reserved.append([f, t])


def reserve_ports(ports):
    with open(ports_path(), "r+") as fd:
        reserved = json.load(fd)
        fd.seek(0)
        fd.truncate()

        for port in ports:
            if type(port) is tuple:
                reserve_single_range(reserved, port)
            else:
                reserve_single_range(reserved, (port, port))

        json.dump(reserved, fd)


def release_ports(ports):
    with open(ports_path(), "r+") as fd:
        reserved = json.load(fd)
        for port in ports:
            if type(port) is tuple:
                release_single_range(reserved, port)
            else:
                release_single_range(reserved, (port, port))
        fd.seek(0)
        fd.truncate()
        json.dump(reserved, fd)


# endregion

# region systemd service
def register_systemd_service(project_id):
    subprocess.Popen(
        ["/usr/bin/systemctl", "enable", service_path(project_id)]).wait()


def start_systemd_service(project_id):
    subprocess.Popen(
        ["/usr/bin/systemctl", "start", f"pv-{project_id}-launcher.service"]).wait()


def restart_systemd_service(project_id):
    subprocess.Popen(
        ["/usr/bin/systemctl", "restart", f"pv-{project_id}-launcher.service"]).wait()


def remove_systemd_service(project_id):
    subprocess.Popen(
        ["/usr/bin/systemctl", "stop", f"pv-{project_id}-launcher.service"]).wait()
    subprocess.Popen(
        ["/usr/bin/systemctl", "disable", f"pv-{project_id}-launcher.service"]).wait()


# endregion

# region launchers.txt
def add_launcher(project_id, launcher_port):
    with open(f"/srv/pv-configurator/launchers.txt", "a") as fd:
        fd.write(f"{project_id} localhost:{launcher_port}\n")


def remove_launcher(project_id):
    with open(f"/srv/pv-configurator/launchers.txt", "r+") as fd:
        lines = fd.readlines()
        fd.seek(0)
        fd.truncate()
        lines_filtered = [line for line in lines if not line.startswith(f"{project_id} ")]
        fd.writelines(lines_filtered)


# endregion

# region projects.json
def add_project_to_user(username, project_id):
    with open(projects_dir_path(), "r+") as fd:
        data = json.load(fd)
        if username in data:
            data[username].append(project_id)
        else:
            data[username] = [project_id]
        fd.seek(0)
        fd.truncate()
        json.dump(data, fd)


def remove_project_from_user(username, project_id):
    with open(projects_dir_path(), "r+") as fd:
        data = json.load(fd)
        projects = data[username]
        projects_filtered = [project for project in projects if project != project_id]
        if len(projects_filtered) == 0:
            data.pop(username)
        else:
            data[username] = projects_filtered
        fd.seek(0)
        fd.truncate()
        json.dump(data, fd)


def projects_of_user(username):
    with open(projects_dir_path(), "r") as fd:
        projects = json.load(fd)
        if username in projects:
            return projects[username]
        else:
            return []


def check_belongs_to_user(username, project_id):
    if project_id not in projects_of_user(username):
        print("Invalid project")
        sys.exit(1)


# endregion

def project_url(project_id, servername):
    return f"http://{servername}/?sessionManagerURL=http://{servername}/project/{project_id}"


def create(username, settings, args):
    project_id = generate_project_id()

    with open(ports_path(), "r") as fd:
        reserved = json.load(fd)
    launcher_port, port_ranges = get_free_ports(reserved, 6)

    # TODO validate dataDir
    launcher_conf = launcher_config(username, settings, project_id, launcher_port, port_ranges, args.dataDir,
                                    args.loadFile)
    project_vals = project_values(launcher_port, port_ranges, args.dataDir, args.loadFile)
    try:
        os.mkdir(f"/var/log/paraview-launcher/{project_id}")
        os.chown(f"/var/log/paraview-launcher/{project_id}", pwd.getpwnam("pv-launcher").pw_uid,
                 pwd.getpwnam("pv-launcher").pw_gid, follow_symlinks=False)
    except FileExistsError:
        pass

    # projects/<id>
    # root:pv-launcher rwx --x ---
    os.mkdir(project_path(project_id))
    os.chown(project_path(project_id), -1, grp.getgrnam("pv-launcher").gr_gid,
             follow_symlinks=False)
    os.chmod(project_path(project_id), stat.S_IRWXU | stat.S_IXGRP, follow_symlinks=False)

    reserve_ports([launcher_port] + port_ranges)

    # create empty project-proxies/*.proxy.txt file
    # pv-launcher:pv-session-mapper  rw- r-- ---
    with open(sessions_path(project_id), "a"):
        pass
    os.chown(sessions_path(project_id), pwd.getpwnam("pv-launcher").pw_uid, grp.getgrnam("pv-session-mapper").gr_gid,
             follow_symlinks=False)
    chmod_rw_r(sessions_path(project_id))

    # <id>/launcher_config.json
    # root:pv-launcher rw- r-- ---
    with open(launcher_config_path(project_id), "w") as fd:
        json.dump(launcher_conf, fd)
    os.chown(launcher_config_path(project_id), -1, grp.getgrnam("pv-launcher").gr_gid,
             follow_symlinks=False)
    chmod_rw_r(launcher_config_path(project_id))

    # <id>/config.json
    # root:root rw- --- ---
    with open(project_config_path(project_id), "w") as fd:
        json.dump(project_vals, fd)
    chmod_rw_only(project_config_path(project_id))

    # <id>/*.service
    # root:root rw- --- ---
    with open(service_path(project_id), "w") as fd:
        fd.write(systemd_unit(username, settings, project_id))
    chmod_rw_only(service_path(project_id))

    add_launcher(project_id, launcher_port)
    add_project_to_user(username, project_id)

    register_systemd_service(project_id)
    start_systemd_service(project_id)
    print(f"New project: {project_id}, Open browser at")
    print(project_url(project_id, settings.servername))


def edit(username, settings, args):
    project_id = args.id
    check_belongs_to_user(username, project_id)

    with open(project_config_path(project_id)) as fd:
        config_conf = json.load(fd)

    launcher_port = config_conf["port"]
    port_ranges = config_conf["port_ranges"]
    if args.dataDir is not None:
        dataDir = args.dataDir
    else:
        dataDir = config_conf["dataDir"]

    if args.loadFile is not None:
        loadFile = args.loadFile
    elif args.noLoadFile:
        loadFile = None
    else:
        loadFile = config_conf["loadFile"]

    launcher_conf = launcher_config(username, settings, project_id, launcher_port, port_ranges, dataDir, loadFile)
    config_conf = project_values(launcher_port, port_ranges, dataDir, loadFile)
    with open(launcher_config_path(project_id), "w") as fd:
        json.dump(launcher_conf, fd)
    with open(project_config_path(project_id), "w") as fd:
        json.dump(config_conf, fd)

    restart_systemd_service(project_id)


def remove(username, args):
    project_id = args.id
    check_belongs_to_user(username, project_id)
    remove_systemd_service(project_id)
    with open(project_config_path(project_id)) as fd:
        config_conf = json.load(fd)
    launcher_port = config_conf["port"]
    port_ranges = config_conf["port_ranges"]
    port_ranges = [(f, t) for [f, t] in port_ranges]
    remove_project_from_user(username, project_id)
    remove_launcher(project_id)
    os.remove(service_path(project_id))
    os.remove(project_config_path(project_id))
    os.remove(launcher_config_path(project_id))
    os.remove(sessions_path(project_id))
    release_ports([launcher_port] + port_ranges)
    os.rmdir(project_path(project_id))


def list_projects(username, args):
    projects = projects_of_user(username)
    if projects is None or len(projects) == 0:
        print("You have no published projects")
        return
    for project in projects:
        with open(project_config_path(project)) as fd:
            config_conf = json.load(fd)
            dataDir = config_conf["dataDir"]
            print(f"{project}\t{dataDir}")


def show_project(username, settings, args):
    project_id = args.id
    check_belongs_to_user(username, project_id)
    with open(project_config_path(project_id)) as fd:
        config_conf = json.load(fd)
        dataDir = config_conf["dataDir"]
        loadFile = config_conf["loadFile"]
        print(f"ID: {project_id}")
        print(f"Directory: {dataDir}")
        if loadFile is None:
            print(f"No default file")
        else:
            print(f"Default file:\t{loadFile}")
        print(f"Link: {project_url(project_id, settings.servername)}")


def resolve_data_dir_in_args(args):
    try:
        args.dataDir = os.path.abspath(args.dataDir)
    except AttributeError:
        pass


def parse_args(args=None):
    parser = argparse.ArgumentParser(prog="pvconfig")
    subparsers = parser.add_subparsers(help="subcommands", required=True, dest="subcommand")

    create_parser = subparsers.add_parser("publish", help="publish a project online")
    create_parser.add_argument("-d", "--dataDir", metavar="DIR", required=True,
                               help="Which directory should be "
                                    "published (required)")
    create_parser.add_argument("-f", "--loadFile", metavar="FILE",
                               help="Open this file by default (none if omitted)")

    edit_parser = subparsers.add_parser("modify", help="edit settings for a published project")
    edit_parser.add_argument("id", metavar="ID", help="The project ID (see the \"list\" subcommand)")
    edit_parser.add_argument("-d", "--dataDir", metavar="DIR", help="Which directory should be "
                                                                    "published")
    load_file_group = edit_parser.add_mutually_exclusive_group(required=False)
    load_file_group.add_argument("-f", "--loadFile", metavar="FILE",
                                 help="Open this file by default")
    load_file_group.add_argument("--noLoadFile", help="Don't load a file by default", action="store_true")

    subparsers.add_parser("list", help="list all published projects")

    show_parser = subparsers.add_parser("show", help="show properties of a project")
    show_parser.add_argument("id", metavar="ID", help="The project ID (see the \"list\" subcommand)")

    delete_parser = subparsers.add_parser("unpublish", help="unpublish your published project")
    delete_parser.add_argument("id", metavar="ID", help="The project ID (see the \"list\" subcommand)")

    return parser.parse_args(args)


class Settings:
    def __init__(self, dic):
        self.servername = dic["servername"]
        self.python_exec = dic["python_exec"]
        self.visualizer_exec = dic["visualizer_exec"]
        self.launcher_exec = dic["launcher_exec"]


def chmod_rw_r(path):
    """chmod 640"""
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP, follow_symlinks=False)


def chmod_rw_only(path):
    """chmod 600"""
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR, follow_symlinks=False)


def init_files():
    try:
        os.mkdir("/srv/pv-configurator/projects")
        os.chown("/srv/pv-configurator/projects", -1, grp.getgrnam("pv-launcher").gr_gid,
                 follow_symlinks=False)
        # rwx --x ---
        os.chmod("/srv/pv-configurator/projects", stat.S_IRWXU | stat.S_IXGRP, follow_symlinks=False)
    except FileExistsError:
        pass

    try:
        os.mkdir("/srv/pv-configurator/project-proxies")
        os.chown("/srv/pv-configurator/project-proxies", pwd.getpwnam("pv-launcher").pw_uid,
                 grp.getgrnam("pv-session-mapper").gr_gid, follow_symlinks=False)
        # rwx r-x ---
        os.chmod("/srv/pv-configurator/project-proxies", stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP,
                 follow_symlinks=False)
    except FileExistsError:
        pass
    try:
        os.mkdir("/var/log/paraview-launcher")
    except FileExistsError:
        pass

    try:
        with open(projects_dir_path(), "x") as projects_json:
            projects_json.write("{}")
        chmod_rw_only(projects_dir_path())
    except FileExistsError:
        pass
    try:
        with open(ports_path(), "x") as ports_json:
            ports_json.write("[]")
        chmod_rw_only(projects_dir_path())
    except FileExistsError:
        pass


def main(username, args):
    init_files()
    with open(settings_file(), "r") as file:
        settings = Settings(json.load(file))

    resolve_data_dir_in_args(args)

    with FileLock("/srv/pv-configurator/lock.lock"):
        if args.subcommand == "publish":
            create(username, settings, args)
        elif args.subcommand == "modify":
            edit(username, settings, args)
        elif args.subcommand == "list":
            list_projects(username, args)
        elif args.subcommand == "show":
            show_project(username, settings, args)
        elif args.subcommand == "unpublish":
            remove(username, args)
        else:
            print("Unsupported subcommand")
            return


if __name__ == '__main__':
    user = os.getenv("SUDO_USER")
    main(user, parse_args())
