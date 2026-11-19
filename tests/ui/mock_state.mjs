// The same data as docs/mockup/main_window.png, used to compare the real UI with the mockup.
const GB = 1024 ** 3, MB = 1024 ** 2;
const now = Date.now() / 1000, day = 86400;
// Weekday offsets so "Mon"/"Sun" show like the mockup regardless of today's date.
const back = (wd) => { const d = new Date(); let n = (d.getDay() - wd + 7) % 7; if (n < 2) n += 7; return now - n * day; };

function dl(o) {
  return {
    id: o.filename, url: `https://${o.host}/${o.filename}`, page_url: "", kind: o.kind || "http",
    filename: o.filename, title: "", quality: "", badge: o.badge, host: o.host, category: o.category,
    size: o.size, size_exact: true, downloaded: Math.round(o.size * o.progress), progress: o.progress,
    status: o.status, error: o.error || "", resumable: true, speed: o.speed || 0, eta: o.eta ?? null,
    connections: o.connections || [], max_connections: 8, parts_total: 0, parts_done: 0,
    save_dir: o.save_dir || "D:\\Downloads\\" + o.category, path: "", added: o.added, finished_at: null, in_queue: true,
  };
}

export const mockState = {
  downloads: [
    dl({ filename: "ubuntu-24.04-desktop.iso", host: "releases.example.org", badge: "ISO", category: "Compressed", size: 5.9 * GB, progress: 0.62, status: "downloading", speed: 11.3 * MB, eta: 372, added: now - 60, connections: [0.95, 0.62, 0.80, 0.50, 0.72, 0.40, 0.88, 0.55] }),
    dl({ filename: "Lecture_Series_Ep12.mp4", host: "media.example.com", badge: "MP4", category: "Video", size: 842 * MB, progress: 0.38, status: "downloading", speed: 4.8 * MB, eta: 167, added: now - 120 }),
    dl({ filename: "dataset_v3.zip", host: "data.example.net", badge: "ZIP", category: "Compressed", size: 1.2 * GB, progress: 0.91, status: "downloading", speed: 8.1 * MB, eta: 13, added: now - 180 }),
    dl({ filename: "setup_installer.exe", host: "cdn.example.com", badge: "EXE", category: "Programs", size: 96 * MB, progress: 1, status: "complete", added: now - day }),
    dl({ filename: "report_Q3.pdf", host: "files.example.org", badge: "PDF", category: "Documents", size: 4.2 * MB, progress: 1, status: "complete", added: now - day - 60 }),
    dl({ filename: "podcast_ep45.mp3", host: "audio.example.com", badge: "MP3", category: "Music", size: 58 * MB, progress: 0.24, status: "paused", added: back(1) }),
    dl({ filename: "backup_2026.tar.gz", host: "backup.example.net", badge: "GZ", category: "Compressed", size: 3.4 * GB, progress: 0.17, status: "error", error: "Timeout", added: back(1) - 60 }),
    dl({ filename: "trailer_1080p.m3u8", host: "stream.example.com", badge: "HLS", kind: "hls", category: "Video", size: 212 * MB, progress: 0, status: "queued", added: back(0) }),
  ],
  counts: { all: 12, categories: { Compressed: 4, Documents: 2, Music: 1, Programs: 3, Video: 5 }, unfinished: 7, finished: 5, queues: 2, grabber: 1 },
  active: 3, total_speed: 24.2 * MB, waiting: 1, queue_running: true, scheduler: "Scheduler off",
  settings: { speed_limit: 2 * MB, api_port: 52817, connections: 8, max_active: 3, download_dir: "D:\\Downloads",
    file_by_category: true, scheduler_enabled: false, scheduler_start: "02:00", scheduler_stop: "07:00" },
  features: { sites: true, ffmpeg: true },
};
