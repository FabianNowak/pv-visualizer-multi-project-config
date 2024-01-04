use std::fs::DirEntry;
use std::path::{Path};

pub struct Project {
    pub name: String,
    pub mappings: Vec<Mapping>,
}

pub struct Mapping {
    pub session_id: String,
    pub host: String,
}

pub fn load_test_inputs<P: AsRef<Path>>(dir: P) -> Vec<Project> {
    let subfiles: Vec<DirEntry> = std::fs::read_dir(dir)
        .expect("could not access test input directory")
        .map(|e| e.expect("could not get next subdirectory"))
        .collect();

    subfiles.iter()
        .map(|entry| {
            let project_id = entry.file_name()
                .to_string_lossy()
                .strip_suffix(".proxy.txt")
                .expect(&format!("File {:?} did not end with \".proxy.txt\"", &entry.file_name()))
                .to_string();
            let proxytxt = entry.path();
            let proxytxt_content = std::fs::read_to_string(&proxytxt).expect(&format!("read {:?} failed", &proxytxt));
            let mappings: Vec<Mapping> = proxytxt_content.lines().map(line_to_mapping).collect();
            return Project { name: project_id, mappings };
        })
        .collect()
}

fn line_to_mapping(line: &str) -> Mapping {
    let mut split = line.split_ascii_whitespace();
    let id = split.next().unwrap();
    let host = split.next().unwrap();
    Mapping {
        session_id: id.to_owned(),
        host: host.to_owned(),
    }
}