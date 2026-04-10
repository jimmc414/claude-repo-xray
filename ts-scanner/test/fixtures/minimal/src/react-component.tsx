"use client";
import { useState, useEffect } from "react";

export function Counter() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    document.title = `Count: ${count}`;
  }, [count]);
  return <button onClick={() => setCount(c => c + 1)}>{count}</button>;
}

export function formatLabel(text: string): string {
  return text.toUpperCase();
}
