use std::fmt::{Display, Formatter};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ServiceError {
    InvalidInput(String),
    Conflict(String),
    Io(String),
    Storage(String),
}

impl Display for ServiceError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidInput(msg) => write!(f, "invalid input: {msg}"),
            Self::Conflict(msg) => write!(f, "conflict: {msg}"),
            Self::Io(msg) => write!(f, "I/O error: {msg}"),
            Self::Storage(msg) => write!(f, "storage error: {msg}"),
        }
    }
}

impl std::error::Error for ServiceError {}

pub type ServiceResult<T> = Result<T, ServiceError>;
