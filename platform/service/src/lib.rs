#![forbid(unsafe_code)]

pub mod catalog;
pub mod config;
pub mod dashboard;
pub mod db;
pub mod dispatch;
pub mod error;
pub mod events;
pub mod git;
pub mod payloads;
pub mod pandoc;
pub mod plans;
pub mod reconcile;
pub mod results;
pub mod service;
pub mod sync;
pub mod types;

pub use error::{ServiceError, ServiceResult};
pub use service::Service;
