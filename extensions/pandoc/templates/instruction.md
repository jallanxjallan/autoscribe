---
slug:
class:
kind:
status:

---

```create-note-runtime
const instructionTypeChoices = [
  { label: "Global", value: "global", prefix: "gbl" },
  { label: "Context", value: "context", prefix: "cxt" },
  { label: "Specific", value: "specific", prefix: "spc" },
];

const qa = params.quickAddApi || params.quickAdd || null;
let selectedInstructionType = null;

if (qa && typeof qa.suggester === "function") {
  selectedInstructionType = await qa.suggester(
    instructionTypeChoices.map((item) => item.label),
    instructionTypeChoices,
    "Pick instruction type",
  );
}

if (!selectedInstructionType && typeof window !== "undefined" && typeof window.prompt === "function") {
  const rawSelection = String(window.prompt("Instruction type: global, context, or specific", "specific") || "")
    .trim()
    .toLowerCase();
  selectedInstructionType =
    instructionTypeChoices.find((item) => item.value === rawSelection) ||
    instructionTypeChoices.find((item) => item.prefix === rawSelection) ||
    null;
}

if (!selectedInstructionType) {
  throw new Error("Instruction type selection requires QuickAdd suggester support.");
}

await helpers.initializeCreatedNote({
  file,
  noteType: "instruction",
  parts: { type: selectedInstructionType.prefix },
});
```

# Instruction
