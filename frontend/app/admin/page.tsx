"use client";

import { Card, CardContent } from "@/components/ui/card";
import { RequireAuth } from "@/lib/auth";

const settings = [
  {
    label: "Auth provider",
    value: "Supabase"
  },
  {
    label: "Document corpus",
    value: "3 sources connected"
  },
  {
    label: "Audit logs",
    value: "Retention: 365 days"
  }
];

export default function AdminPage() {
  return (
    <RequireAuth>
      <div className="space-y-6">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold text-ink-900">Admin</h1>
          <p className="text-sm text-ink-600">
            Manage policies, access, and system configuration.
          </p>
        </header>
        <div className="grid gap-4">
          {settings.map((setting) => (
            <Card key={setting.label}>
              <CardContent className="flex items-center justify-between">
                <p className="text-sm font-semibold text-ink-900">
                  {setting.label}
                </p>
                <span className="text-sm text-ink-600">{setting.value}</span>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </RequireAuth>
  );
}
