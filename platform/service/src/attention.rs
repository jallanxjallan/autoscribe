use crate::{ServiceError, ServiceResult};
use std::{
    env,
    fs,
    io::{Read, Write},
    os::unix::{fs::PermissionsExt, net::{UnixListener, UnixStream}},
    path::{Path, PathBuf},
};

const DEFAULT_SOCKET_NAME: &str = "autoscribe-service.sock";

/// Return the local, user-scoped socket used for repository-attention hints.
pub fn socket_path() -> PathBuf {
    env::var_os("AUTOSCRIBE_SERVICE_SOCKET")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            env::var_os("XDG_RUNTIME_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(env::temp_dir)
                .join(DEFAULT_SOCKET_NAME)
        })
}

/// Send repository candidates to the running system worker.
///
/// The adapter need not prove that a path is a Git root. The worker owns that
/// validation and canonicalisation boundary.
pub fn send(paths: &[PathBuf]) -> ServiceResult<()> {
    if paths.is_empty() {
        return Err(ServiceError::InvalidInput(
            "attention requires at least one repository path".into(),
        ));
    }
    let mut stream = UnixStream::connect(socket_path()).map_err(|error| {
        ServiceError::Io(format!(
            "could not contact autoscribe-service: {error}"
        ))
    })?;
    for path in paths {
        let path_text = path.to_string_lossy();
        let line = serde_json::to_string(path_text.as_ref())
            .map_err(|error| ServiceError::InvalidInput(error.to_string()))?;
        writeln!(stream, "{line}").map_err(io)?;
    }
    Ok(())
}

#[derive(Debug)]
pub struct AttentionListener {
    listener: UnixListener,
    path: PathBuf,
}

impl AttentionListener {
    pub fn bind() -> ServiceResult<Self> {
        let path = socket_path();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(io)?;
        }
        if path.exists() {
            fs::remove_file(&path).map_err(io)?;
        }
        let listener = UnixListener::bind(&path).map_err(io)?;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).map_err(io)?;
        listener.set_nonblocking(true).map_err(io)?;
        Ok(Self { listener, path })
    }

    /// Drain all complete hints currently waiting on the socket.
    pub fn drain(&self) -> ServiceResult<Vec<PathBuf>> {
        let mut paths = Vec::new();
        loop {
            match self.listener.accept() {
                Ok((mut stream, _address)) => {
                    let mut payload = String::new();
                    stream.read_to_string(&mut payload).map_err(io)?;
                    for line in payload.lines().map(str::trim).filter(|line| !line.is_empty()) {
                        let path: String = serde_json::from_str(line).map_err(|error| {
                            ServiceError::InvalidInput(format!(
                                "invalid repository-attention message: {error}"
                            ))
                        })?;
                        paths.push(PathBuf::from(path));
                    }
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => break,
                Err(error) => return Err(io(error)),
            }
        }
        Ok(paths)
    }

    pub fn path(&self) -> &Path {
        &self.path
    }
}

impl Drop for AttentionListener {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn io(error: std::io::Error) -> ServiceError {
    ServiceError::Io(error.to_string())
}
