"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Shield, UserCheck } from "lucide-react";
import { Button, ConfirmDialog } from "@/components/ui/Modal";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { User } from "@/lib/types";

export default function UserManagementPage() {
  const { user: currentAdmin } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [targetUser, setTargetUser] = useState<User | null>(null);
  const [newRole, setNewRole] = useState<"user" | "admin" | null>(null);
  const [selectedUserIds, setSelectedUserIds] = useState<Set<string>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; isError?: boolean } | null>(null);

  const loadUsers = useCallback(async () => {
    try {
      const res = await api.listUsers(0, 100);
      setUsers(res.users);
      setTotal(res.total);
    } catch {
      setStatusMessage({ text: "Failed to load user accounts.", isError: true });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    api
      .listUsers(0, 100)
      .then((res) => {
        if (active) {
          setUsers(res.users);
          setTotal(res.total);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setStatusMessage({ text: "Failed to load user accounts.", isError: true });
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleRoleChange() {
    if (!targetUser || !newRole) return;
    try {
      await api.updateUserRole(targetUser.id, newRole);
      setStatusMessage({
        text: `Role for ${targetUser.email} updated to ${newRole}.`,
        isError: false,
      });
      await loadUsers();
    } catch (err) {
      setStatusMessage({
        text: err instanceof Error ? err.message : "Failed to update role.",
        isError: true,
      });
    } finally {
      setTargetUser(null);
      setNewRole(null);
    }
  }

  async function handleBulkDelete() {
    if (selectedUserIds.size === 0) return;
    try {
      await api.bulkDeleteUsers([...selectedUserIds]);
      setSelectedUserIds(new Set());
      setStatusMessage({ text: "Selected user accounts were permanently deleted." });
      await loadUsers();
    } catch (err) {
      setStatusMessage({
        text: err instanceof Error ? err.message : "Failed to delete selected users.",
        isError: true,
      });
    }
  }

  const selectableUsers = users.filter((user) => user.id !== currentAdmin?.id);
  const allUsersSelected =
    selectableUsers.length > 0 && selectableUsers.every((user) => selectedUserIds.has(user.id));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight">Users & Role Management</h1>
          <p className="font-sub mt-1 text-sm text-muted">
            Inspect registered accounts, view permissions, and assign administrator privileges.
          </p>
        </div>
        <span className="font-sub text-xs text-muted">
          Total Users: <strong className="text-text">{total}</strong>
        </span>
      </div>

      {selectedUserIds.size > 0 && (
        <div className="flex items-center justify-between rounded-xl border border-error/30 bg-error/5 px-4 py-3">
          <span className="text-sm text-error">
            {selectedUserIds.size} user{selectedUserIds.size === 1 ? "" : "s"} selected
          </span>
          <Button variant="danger" onClick={() => setBulkDeleteOpen(true)} className="text-xs">
            Delete Selected
          </Button>
        </div>
      )}

      {statusMessage && (
        <div
          className={`flex items-center gap-2 rounded-xl p-3.5 text-sm ${
            statusMessage.isError
              ? "border border-error/30 bg-error/5 text-error"
              : "border border-success/30 bg-success/5 text-success"
          }`}
        >
          {statusMessage.isError ? (
            <AlertCircle className="size-4 shrink-0" />
          ) : (
            <CheckCircle2 className="size-4 shrink-0" />
          )}
          <span>{statusMessage.text}</span>
        </div>
      )}

      {/* Users Table */}
      <div className="overflow-hidden rounded-2xl border border-border bg-background shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-surface text-xs font-semibold text-muted uppercase tracking-wider">
              <tr>
                <th className="w-12 px-5 py-3.5">
                  <input
                    type="checkbox"
                    checked={allUsersSelected}
                    onChange={(event) => {
                      setSelectedUserIds(
                        event.target.checked
                          ? new Set(selectableUsers.map((user) => user.id))
                          : new Set(),
                      );
                    }}
                    aria-label="Select all visible users except yourself"
                  />
                </th>
                <th className="px-5 py-3.5">User</th>
                <th className="px-4 py-3.5">Email</th>
                <th className="px-4 py-3.5">Role</th>
                <th className="px-4 py-3.5">Registered</th>
                <th className="px-5 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-muted">
                    Loading users...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-muted">
                    No users found.
                  </td>
                </tr>
              ) : (
                users.map((u) => {
                  const isCurrent = u.id === currentAdmin?.id;
                  const isAdmin = u.role === "admin";

                  return (
                    <tr key={u.id} className="transition hover:bg-surface/50">
                      <td className="px-5 py-4">
                        <input
                          type="checkbox"
                          checked={selectedUserIds.has(u.id)}
                          disabled={isCurrent}
                          onChange={(event) => {
                            setSelectedUserIds((current) => {
                              const next = new Set(current);
                              if (event.target.checked) next.add(u.id);
                              else next.delete(u.id);
                              return next;
                            });
                          }}
                          aria-label={`Select ${u.email}`}
                        />
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <span className="font-heading flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
                            {(u.full_name || u.email)[0]?.toUpperCase()}
                          </span>
                          <div>
                            <p className="font-heading text-sm font-semibold text-text">
                              {u.full_name || "Unnamed"}
                            </p>
                            {isCurrent && (
                              <span className="font-sub text-[10px] text-accent font-medium">
                                (You)
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4 font-sub text-xs text-text">{u.email}</td>
                      <td className="px-4 py-4">
                        <span
                          className={`inline-flex items-center gap-1 rounded-md px-2.5 py-0.5 text-xs font-medium ${
                            isAdmin
                              ? "bg-accent-soft text-accent"
                              : "bg-surface text-muted"
                          }`}
                        >
                          {isAdmin ? (
                            <Shield className="size-3" />
                          ) : (
                            <UserCheck className="size-3" />
                          )}
                          {isAdmin ? "Admin" : "Student"}
                        </span>
                      </td>
                      <td className="px-4 py-4 font-sub text-xs text-muted">
                        {new Date(u.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </td>
                      <td className="px-5 py-4 text-right">
                        {isCurrent ? (
                          <span className="text-xs text-muted">Protected</span>
                        ) : (
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setTargetUser(u);
                              setNewRole(isAdmin ? "user" : "admin");
                            }}
                            className="text-xs"
                          >
                            {isAdmin ? "Demote to Student" : "Promote to Admin"}
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmDialog
        open={!!targetUser}
        onClose={() => {
          setTargetUser(null);
          setNewRole(null);
        }}
        onConfirm={handleRoleChange}
        title={newRole === "admin" ? "Promote User to Admin?" : "Demote User to Regular Student?"}
        description={`Are you sure you want to change the role of ${targetUser?.email} to ${newRole}?`}
        confirmLabel={newRole === "admin" ? "Promote" : "Demote"}
      />
      <ConfirmDialog
        open={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        onConfirm={handleBulkDelete}
        title="Delete Selected Users?"
        description={`${selectedUserIds.size} selected user account${selectedUserIds.size === 1 ? "" : "s"} and their related data will be permanently deleted.`}
        confirmLabel="Delete Selected"
      />
    </div>
  );
}
