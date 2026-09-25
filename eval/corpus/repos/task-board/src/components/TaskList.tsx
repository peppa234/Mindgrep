import { DndContext, DragEndEvent, closestCenter } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";

import { formatRelativeTime, isOverdue } from "../lib/dates";
import { Status, Task, useTaskStore } from "../store/tasks";

function TaskCard({ task }: { task: Task }) {
  const { attributes, listeners, setNodeRef, transform } = useSortable({ id: task.id });
  const due = task.due ? new Date(task.due) : null;
  const style = transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined;
  return (
    <li ref={setNodeRef} style={style} {...attributes} {...listeners} className="task-card">
      <span>{task.title}</span>
      {due && <small className={isOverdue(due) ? "overdue" : ""}>{formatRelativeTime(due)}</small>}
    </li>
  );
}

/** One kanban column. Cards can be dragged to reorder them within the column. */
export function TaskList({ status }: { status: Status }) {
  const tasks = useTaskStore((s) =>
    s.tasks.filter((t) => t.status === status).sort((a, b) => a.position - b.position),
  );
  const moveTask = useTaskStore((s) => s.moveTask);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const toIndex = tasks.findIndex((t) => t.id === over.id);
    moveTask(String(active.id), status, toIndex);
  }

  return (
    <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
        <ul className="task-list">
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
        </ul>
      </SortableContext>
    </DndContext>
  );
}
