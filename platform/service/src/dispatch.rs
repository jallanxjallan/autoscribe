use crate::{
    ServiceError, ServiceResult,
    db::Database,
    events::{self, NoticeSink},
    git, sync,
    types::*,
};
use std::{collections::HashSet, path::Path};

pub fn prepare(
    db: &Database,
    repo: &Path,
    request: PrepareSavedDispatchRequest,
) -> ServiceResult<PreparedDispatch> {
    validate_request(&request)?;
    let actual_hash = sha256_hex(&request.payload);
    if actual_hash != request.payload_sha256.to_ascii_lowercase() {
        return Err(ServiceError::Conflict(format!(
            "dispatch payload hash mismatch: expected {}, computed {actual_hash}",
            request.payload_sha256
        )));
    }

    let sink = NoticeSink::new(db);
    events::publish(
        &sink,
        Notice {
            kind: NoticeKind::Accepted,
            operation: "dispatch.prepare".into(),
            message: format!("Preparing dispatch {}", request.dispatch.0),
        },
    )?;

    let paths = request
        .records
        .iter()
        .map(|record| record.path.clone())
        .collect::<Vec<_>>();
    let states = git::inspect(repo, &paths)?;
    let mut dirty_paths = Vec::new();
    for state in states {
        if !state.tracked {
            return Err(ServiceError::InvalidInput(format!(
                "dispatch source is not tracked by Git: {}",
                state.path.display()
            )));
        }
        if state.dirty {
            dirty_paths.push(state.path);
        }
    }

    if !dirty_paths.is_empty() {
        git::commit(
            repo,
            CommitRequest {
                paths: dirty_paths.clone(),
                message: request.commit_message.clone(),
                purpose: CommitPurpose::Lock,
            },
        )?;
    }

    let source_revision = git::head(repo)?;
    let source_branch = git::current_branch(repo)?;
    let branch = git::create_dispatch_branch(
        repo,
        &CreateDispatchBranchRequest {
            dispatch: request.dispatch.clone(),
            source_revision: source_revision.0.clone(),
            source_branch: source_branch.clone(),
            plan: request.plan,
            plan_version: request.plan_version,
            records: request.records,
            payload_sha256: actual_hash.clone(),
        },
    )?;

    sync::enqueue(
        db,
        &SavedPayload {
            dispatch_id: request.dispatch.clone(),
            bytes: request.payload,
            sha256: actual_hash.clone(),
        },
    )?;

    events::publish(
        &sink,
        Notice {
            kind: NoticeKind::Completed,
            operation: "dispatch.prepare".into(),
            message: format!(
                "Prepared dispatch {} on {}",
                request.dispatch.0, branch.name
            ),
        },
    )?;

    Ok(PreparedDispatch {
        dispatch: request.dispatch,
        source_revision,
        source_branch,
        branch,
        payload_sha256: actual_hash,
        committed_paths: dirty_paths,
    })
}

fn validate_request(request: &PrepareSavedDispatchRequest) -> ServiceResult<()> {
    if request.dispatch.0.trim().is_empty()
        || request.plan.0.trim().is_empty()
        || request.plan_version.trim().is_empty()
        || request.payload.is_empty()
        || request.payload_sha256.trim().is_empty()
        || request.commit_message.trim().is_empty()
        || request.records.is_empty()
    {
        return Err(ServiceError::InvalidInput(
            "dispatch, plan, plan version, records, payload, hash, and commit message are required"
                .into(),
        ));
    }
    let mut slugs = HashSet::new();
    let mut paths = HashSet::new();
    for record in &request.records {
        if record.slug.trim().is_empty() {
            return Err(ServiceError::InvalidInput(
                "dispatch record slug is required".into(),
            ));
        }
        if !slugs.insert(record.slug.clone()) {
            return Err(ServiceError::Conflict(format!(
                "duplicate dispatch record slug: {}",
                record.slug
            )));
        }
        if !paths.insert(record.path.clone()) {
            return Err(ServiceError::Conflict(format!(
                "duplicate dispatch record path: {}",
                record.path.display()
            )));
        }
    }
    Ok(())
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    const INITIAL: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let bit_len = (bytes.len() as u64).wrapping_mul(8);
    let mut padded = bytes.to_vec();
    padded.push(0x80);
    while padded.len() % 64 != 56 {
        padded.push(0);
    }
    padded.extend_from_slice(&bit_len.to_be_bytes());
    let mut h = INITIAL;
    for chunk in padded.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (index, word) in chunk.chunks_exact(4).enumerate() {
            w[index] = u32::from_be_bytes(word.try_into().expect("four-byte SHA-256 word"));
        }
        for index in 16..64 {
            let s0 = w[index - 15].rotate_right(7)
                ^ w[index - 15].rotate_right(18)
                ^ (w[index - 15] >> 3);
            let s1 = w[index - 2].rotate_right(17)
                ^ w[index - 2].rotate_right(19)
                ^ (w[index - 2] >> 10);
            w[index] = w[index - 16]
                .wrapping_add(s0)
                .wrapping_add(w[index - 7])
                .wrapping_add(s1);
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh] = h;
        for index in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let t1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[index])
                .wrapping_add(w[index]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let t2 = s0.wrapping_add(maj);
            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(t1);
            d = c;
            c = b;
            b = a;
            a = t1.wrapping_add(t2);
        }
        for (state, value) in h.iter_mut().zip([a, b, c, d, e, f, g, hh]) {
            *state = state.wrapping_add(value);
        }
    }
    h.iter().map(|word| format!("{word:08x}")).collect()
}

pub fn transmit(_identity: &DispatchId) -> ServiceResult<AttemptRecord> {
    Err(ServiceError::NotImplemented("dispatch.transmit"))
}
pub fn poll(_identity: &DispatchId) -> ServiceResult<DispatchView> {
    Err(ServiceError::NotImplemented("dispatch.poll"))
}
pub fn retry(_identity: &DispatchId) -> ServiceResult<AttemptRecord> {
    Err(ServiceError::NotImplemented("dispatch.retry"))
}
pub fn cancel(_identity: &DispatchId) -> ServiceResult<DispatchView> {
    Err(ServiceError::NotImplemented("dispatch.cancel"))
}
pub fn status(_identity: &DispatchId) -> ServiceResult<DispatchView> {
    Err(ServiceError::NotImplemented("dispatch.status"))
}
