import { Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import Dashboard from './pages/Dashboard'
import EventListPage from './pages/EventCase/EventListPage'
import EventDetailPage from './pages/EventCase/EventDetailPage'
import StoryPacketListPage from './pages/StoryPacket/StoryPacketPage'
import StoryPacketDetailPage from './pages/StoryPacket/DetailPage'
import LLMSettingsPage from './pages/Settings/LLMSettingsPage'
import TeamPage from './pages/Settings/TeamPage'
import QueuePage from './pages/SignOffCenter/QueuePage'
import SignOffDetailPage from './pages/SignOffCenter/DetailPage'
import LoginPage from './pages/Auth/LoginPage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<MainLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="events" element={<EventListPage />} />
        <Route path="events/:id" element={<EventDetailPage />} />
        <Route path="story-packets" element={<StoryPacketListPage />} />
        <Route path="story-packets/:id" element={<StoryPacketDetailPage />} />
        <Route path="settings/llm" element={<LLMSettingsPage />} />
        <Route path="settings/team" element={<TeamPage />} />
        <Route path="sign-off" element={<QueuePage />} />
        <Route path="sign-off/:id" element={<SignOffDetailPage />} />
      </Route>
    </Routes>
  )
}

export default App
