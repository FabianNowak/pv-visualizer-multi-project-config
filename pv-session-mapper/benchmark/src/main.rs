use std::io::{BufRead, BufReader, Write};
use std::process::{ChildStdin, ChildStdout, Command, Stdio};
use std::time::{Duration, Instant};
use rand::Rng;
use crate::load_inputs::Project;

mod load_inputs;

fn main() {
    let mut args = std::env::args();
    args.next();
    let exec_path = args.next();
    let exec_path = match exec_path {
        Some(e) => e,
        None => {
            eprintln!("Usage: benchmark <executable> <test directory>");
            return;
        }
    };

    let dir_path = "testdir";
    let inputs = load_inputs::load_test_inputs(dir_path);

    let mut cmd = Command::new(exec_path)
        .arg(dir_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("failed to start session_mapper");
    let mut stdin = cmd.stdin.take().expect("stdin not captured");
    let mut stdout = cmd.stdout.take().expect("stdout not captured");
    for _ in 0..10 {
        println!("{}", measure(&mut stdin, &mut stdout, &inputs).as_millis());
    }
}

struct InOut {
    input: String,
    #[allow(unused)]
    output: String,
}

fn measure(stdin: &mut ChildStdin, stdout: &mut ChildStdout, projects: &Vec<Project>) -> Duration {
    let mut inputs = Vec::new();
    let mut rng = rand::thread_rng();
    //generate inputs
    for _ in 0..1000 {
        let project_idx = rng.gen_range(0..projects.len());
        let project = &projects[project_idx];

        let mapping_idx = rng.gen_range(0..project.mappings.len());
        let mapping = &project.mappings[mapping_idx];

        let session = &mapping.session_id;
        let host = &mapping.host;

        let input = format!("{} {}", project.name, session);
        let output = host.to_owned();
        inputs.push(InOut { input, output })
    }

    let mut stdout = BufReader::new(stdout);
    let mut linebuf = String::new();
    let start = Instant::now();
    for i in inputs {
        linebuf.clear();
        _ = writeln!(stdin, "{}", i.input);
        _ = stdin.flush();
        _ = stdout.read_line(&mut linebuf);
        //assert!(linebuf.starts_with(&i.output), "starts_with() failed: expected_prefix = {}, actual = {}", i.output.escape_debug(), linebuf.escape_debug());
    }
    let duration = start.elapsed();
    return duration;
}
