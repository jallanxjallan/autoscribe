use std::fmt::{Display, Formatter};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ServiceError {
    NotImplemented(&'static str),
    InvalidInput(String),
    Conflict(String),
    Io(String),
    Storage(String),
    Network(String),
}

impl Display for ServiceError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotImplemented(op) => write!(f, "not implemented: {op}"),
            Self::InvalidInput(msg) => write!(f, "invalid input: {msg}"),
            Self::Conflict(msg) => write!(f, "conflict: {msg}"),
            Self::Io(msg) => write!(f, "I/O error: {msg}"),
            Self::Storage(msg) => write!(f, "storage error: {msg}"),
            Self::Network(msg) => write!(f, "network error: {msg}"),
        }
    }
}

impl std::error::Error for ServiceError {}

pub type ServiceResult<T> = Result<T, ServiceError>;

pub(crate) fn stub<T>(operation: &'static str) -> ServiceResult<T> {
    Err(ServiceError::NotImplemented(operation))
}

