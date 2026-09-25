import { create } from "zustand";

export type Status = "todo" | "doing" | "done";

export interface Task {
  id: string;
  title: string;
  status: Status;
  position: number;
  due: string | null;
}

interface TaskState {
  tasks: Task[];
  addTask: (title: string) => void;
  moveTask: (id: string, status: Status, toIndex: number) => void;
  removeTask: (id: string) => void;
}

/** Renumber positions 0..n-1 within one column, keeping the given order. */
function reindex(tasks: Task[]): Task[] {
  return tasks.map((task, index) => ({ ...task, position: index }));
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: [],

  addTask: (title) =>
    set((state) => ({
      tasks: [
        ...state.tasks,
        {
          id: crypto.randomUUID(),
          title,
          status: "todo",
          position: state.tasks.filter((t) => t.status === "todo").length,
          due: null,
        },
      ],
    })),

  // Moving a card between columns: take it out, insert it at toIndex in the target column,
  // then renumber both columns so positions stay dense.
  moveTask: (id, status, toIndex) =>
    set((state) => {
      const moving = state.tasks.find((t) => t.id === id);
      if (!moving) return state;
      const others = state.tasks.filter((t) => t.id !== id);
      const target = others.filter((t) => t.status === status).sort((a, b) => a.position - b.position);
      target.splice(toIndex, 0, { ...moving, status });
      const source = others
        .filter((t) => t.status === moving.status && t.status !== status)
        .sort((a, b) => a.position - b.position);
      const untouched = others.filter((t) => t.status !== status && t.status !== moving.status);
      return { tasks: [...untouched, ...reindex(source), ...reindex(target)] };
    }),

  removeTask: (id) => set((state) => ({ tasks: state.tasks.filter((t) => t.id !== id) })),
}));
