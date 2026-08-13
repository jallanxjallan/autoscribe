use autoscribe_service::{config, pandoc, types::PandocJob, ServiceError};
use std::path::Path;
use std::time::{Duration, Instant};

#[test]
fn unfinished_operations_fail_explicitly() {
    assert_eq!(
        config::load(Path::new("missing.toml")),
        Err(ServiceError::NotImplemented("config.load"))
    );
}

#[test]
fn pandoc_jobs_run_in_parallel_and_retain_input_order() {
    let jobs = vec![
        PandocJob {
            identity: "first".into(),
            working_directory: "/tmp".into(),
            arguments: vec!["-c".into(), "sleep 0.4; printf first".into()],
        },
        PandocJob {
            identity: "second".into(),
            working_directory: "/tmp".into(),
            arguments: vec!["-c".into(), "sleep 0.4; printf second".into()],
        },
    ];

    let started = Instant::now();
    let outcomes = pandoc::run_parallel(Path::new("/bin/sh"), jobs, 2).unwrap();

    assert!(started.elapsed() < Duration::from_millis(700));
    assert_eq!(outcomes[0].identity, "first");
    assert_eq!(outcomes[0].stdout, b"first");
    assert_eq!(outcomes[1].identity, "second");
    assert_eq!(outcomes[1].stdout, b"second");
}

#[test]
fn pandoc_batches_reject_serial_execution() {
    let job = |identity: &str| PandocJob {
        identity: identity.into(),
        working_directory: "/tmp".into(),
        arguments: vec!["-c".into(), "true".into()],
    };
    assert!(matches!(
        pandoc::run_parallel(Path::new("/bin/sh"), vec![job("one"), job("two")], 1),
        Err(ServiceError::InvalidInput(_))
    ));
}
