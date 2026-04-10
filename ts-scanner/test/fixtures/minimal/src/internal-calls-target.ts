function validateInput(x: number): boolean { return x > 0; }

function processItem(item: { value: number }): string {
  if (!validateInput(item.value)) return "invalid";
  return formatResult(item.value);
}

function formatResult(v: number): string { return `Result: ${v}`; }

export { processItem };
