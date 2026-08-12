use autoscribe_service::{config, ServiceError};
use std::path::Path;

#[test]
fn unfinished_operations_fail_explicitly() {
    assert_eq!(
        config::load(Path::new("missing.toml")),
        Err(ServiceError::NotImplemented("config.load"))
    );
}

