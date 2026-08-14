#![forbid(unsafe_code)]

pub mod catalog;
pub mod config;
pub mod dashboard;
pub mod db;
pub mod dispatch;
pub mod error;
pub mod events;
pub mod git;
pub mod instruction_sync;
pub mod pandoc;
pub mod payloads;
pub mod plan_repository;
pub mod plans;
pub mod publish;
pub mod reconcile;
pub mod response_repository;
pub mod results;
pub mod service;
pub mod submit;
pub mod sync;
pub mod types;

pub use error::{ServiceError, ServiceResult};
pub use service::Service;
