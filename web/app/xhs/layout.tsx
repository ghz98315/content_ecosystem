"use client";
import './xhs.css'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import { Sidebar } from '@/components/Sidebar'
import { Task } from '@/lib/types'

export default function XhsLayout({ children }: { children: React.ReactNode }) {
  const [tasks, setTasks] = useState<Task[]>([])

  useEffect(() => {
    const load = async () => {
      const { data } = await supabase
        .from('tasks')
        .select('id, title, source_url, status')
        .order('created_at', { ascending: false })
        .limit(20)
      if (data) setTasks(data as Task[])
    }
    load()
  }, [])

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar tasks={tasks} />
      <main className="flex-1 overflow-y-auto bg-gray-50 min-h-screen">
        {children}
      </main>
    </div>
  )
}
