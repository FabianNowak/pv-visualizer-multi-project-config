use std::path::PathBuf;

const NUM_PROJECTS: usize = 10;
const SESSIONS_PER_PROJECT: usize = 1;

fn main() {
    let dir_path = "testdir";
    _ = std::fs::create_dir(dir_path);
    let is_empty = std::fs::read_dir(dir_path).expect("could not open testdir").next().is_none();
    if !is_empty {
        eprintln!("{} is not an empty directory", dir_path);
        return;
    }
    for _ in 0..NUM_PROJECTS {
        let project_id = uuid::Uuid::new_v4().hyphenated();
        let mut proxy_content = String::new();
        for i in 0..SESSIONS_PER_PROJECT {
            let session_id = uuid::Uuid::new_v4().hyphenated();
            let line = format!("{} localhost:{}\n", session_id, i + 9000);
            proxy_content.push_str(&line);
        }

        let mut path = PathBuf::from(dir_path);
        path.push(project_id.to_string());
        path.set_extension("proxy.txt");

        std::fs::write(&path, &proxy_content)
            .expect(&format!("error writing to {}", path.to_string_lossy()));
    }
}