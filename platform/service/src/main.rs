use autoscribe_service::Service;
use std::{env, path::PathBuf, process::ExitCode};

fn main() -> ExitCode {
    let config = env::args_os().nth(1).map(PathBuf::from).unwrap_or_else(|| PathBuf::from("autoscribe-service.toml"));
    match Service::start(&config) {
        Ok(_) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("autoscribe-service: {error}");
            ExitCode::FAILURE
        }
    }
}

