use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

const NULL: &str = "NULL";

#[cfg(windows)]
#[allow(unused)]
const LOG_FILE: &str = "./session_mapper.log";

#[cfg(not(windows))]
#[allow(unused)]
const LOG_FILE: &str = "/var/log/session_mapper.log";

fn main() {
    log("startup");
    let args: Vec<String> = std::env::args().collect();
    let project_dir = match args.get(1) {
        Some(d) => d,
        None => {
            println!(
                "Missing arguments\nUsage: {} <userDir>",
                args.get(0).map(String::as_str).unwrap_or("session_mapper")
            );
            return;
        }
    };
    let sin = std::io::stdin();
    //Lock stdout for the duration of the program, to avoid locking for every message as the program
    //is single-threaded and there must not be any other output apart from the hostnames
    let mut sout = std::io::stdout().lock();

    let mut buf = String::new();
    loop {
        buf.clear();
        match sin.read_line(&mut buf) {
            Ok(0) => {
                //Input closed
                break;
            }
            Ok(_) => {
                let host = find_local_address(project_dir, &buf);
                match host {
                    None => output(&mut sout, NULL),
                    Some(host) => {
                        output(&mut sout, &host);
                    }
                }
                // Flush to ensure the messages reach Apache immediately
                sout.flush().expect("Flush failed");
            }
            Err(e) => {
                eprintln!("Error reading input: {}", e);
            }
        }
    }
}

fn read_file_contents(proxy_file: impl AsRef<Path>) -> Result<String, ()> {
    let mut file = match fs::File::open(&proxy_file) {
        Ok(f) => f,
        Err(e) => {
            log(&format!(
                "Error opening file {:?}: {}",
                proxy_file.as_ref(),
                e
            ));
            return Err(());
        }
    };

    let mut file_contents = String::new();
    if let Err(e) = file.read_to_string(&mut file_contents) {
        log(&format!(
            "Error reading file {:?}: {}",
            proxy_file.as_ref(),
            e
        ));
        return Err(());
    }
    return Ok(file_contents);
}

fn find_local_address<'a>(projects_dir: &str, project_and_session: &str) -> Option<String> {
    // Don't handle excessively long inputs
    if project_and_session.len() > 100 {
        return None;
    }

    //Split on whitespace
    let mut split = project_and_session.split_ascii_whitespace();
    let project_opt = split.next();
    let session_opt = split.next();
    let too_much = split.next();
    log(project_and_session);
    log(&format!(
        "Project: {:?}, session: {:?}, remainder: {:?}",
        project_opt, session_opt, too_much,
    ));

    //Check if there were exactly two input components and get them out of their Options
    let (project, session) = match (project_opt, session_opt, too_much) {
        (Some(p), Some(s), None) => (p, s),
        _ => {
            return None;
        }
    };

    // Sanitize project id
    if project.contains('/') {
        log("Invalid character detected in project id");
        return None;
    }

    // Construct path for the responsible proxy.txt file
    // <projects_dir>/<project_id>.proxy.txt
    let mut proxy_file = PathBuf::from(projects_dir);
    proxy_file.push(project);
    proxy_file.set_extension("proxy.txt");

    let file_contents = match read_file_contents(&proxy_file) {
        Ok(s) => s,
        Err(_) => {
            return None;
        }
    };

    let host = match file_contents
        .lines()
        .find_map(|l| match_session_and_get_host(l, session))
    {
        Some(host) => host,
        None => {
            return None;
        }
    };

    return Some(host.to_owned());
}

/// Checks if a `line` of a `proxy.txt` file starts with `search_session`.
/// Returns `None` if the line doesn't match.
/// Returns the second part of the line (the hostname and port) if the first part matches `search_session`
fn match_session_and_get_host<'a>(line: &'a str, search_session: &str) -> Option<&'a str> {
    // This function assumes correct format of proxy.txt, as content should only be written by
    // the wslink Launcher application and does not contain user-generated values.
    let mut parts = line.split_ascii_whitespace();
    let session = parts.next();
    let host = parts.next();
    if session == Some(search_session) {
        host
    } else {
        None
    }
}

/// Prints `txt` to `sout` and possibly logs if `cfg(feature="log")` is active
fn output(sout: &mut impl Write, txt: &str) {
    log(&format!("Output: {}", txt));
    writeln!(sout, "{}", txt).expect("write to stdout failed");
}

/// Append `str` to `LOG_FILE`
#[cfg(feature = "log")]
fn log(str: &str) {
    let mut file = fs::File::options()
        .append(true)
        .create(true)
        .open(LOG_FILE)
        .unwrap();
    writeln!(file, "{}", str).unwrap();
}

#[cfg(not(feature = "log"))]
fn log(_: &str) {
    //no-op
}
