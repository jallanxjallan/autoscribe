use autoscribe_service::{
    publish, submit,
    types::ExternalFileRequest,
    ServiceError,
};

#[test]
fn submit_has_a_dedicated_branch_and_remains_a_stub() {
    assert_eq!(submit::BRANCH_REF, "refs/heads/autoscribe/submit");
    assert_eq!(
        submit::submit(request()),
        Err(ServiceError::NotImplemented("submit.submit"))
    );
}

#[test]
fn publish_has_a_dedicated_branch_and_remains_a_stub() {
    assert_eq!(publish::BRANCH_REF, "refs/heads/autoscribe/publish");
    assert_eq!(
        publish::publish(request()),
        Err(ServiceError::NotImplemented("publish.publish"))
    );
}

fn request() -> ExternalFileRequest {
    ExternalFileRequest {
        target: "external-target".into(),
        files: vec!["draft.md".into()],
    }
}
