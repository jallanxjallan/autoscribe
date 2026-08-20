"use strict";

const { serviceCall } = require("./dispatch-service.js");
const { loadConfig } = require("./config-loader.js");

async function readSystemState(app) {
  const state = { refreshed_at: new Date().toISOString(), git: null, pipeline: null, errors: {} };
  try {
    const spec = loadConfig("protocol").service_operations?.system_snapshot || {};
    const response = await serviceCall(app, String(spec.command), { version: Number(spec.request_version) });
    const output = JSON.parse(String(response.stdout || "{}").trim() || "{}");
    if (!output.ok) throw new Error(output.error || "System snapshot failed");
    state.git = output.git || null;
    const pipeline = output.pipeline || {};
    state.pipeline = {
      counts: {
        total: Number(pipeline.active_dispatches || 0),
        unclaimed: Number(pipeline.pending_uploads || 0),
        waiting: Math.max(0, Number(pipeline.active_dispatches || 0) - Number(pipeline.pending_responses || 0)),
        response_pending: Number(pipeline.pending_responses ?? pipeline.pending_files ?? 0),
        uncertain: Number(pipeline.uncertain_uploads || 0),
        reviewed: 0,
      },
      handoffs: [],
    };
  } catch (error) {
    state.errors.service = error?.message || String(error);
    state.errors.git = state.errors.service;
    state.errors.pipeline = state.errors.service;
  }
  return state;
}

module.exports = { readSystemState };
