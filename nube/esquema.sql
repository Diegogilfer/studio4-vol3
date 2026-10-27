-- Studio 4 en la nube (Supabase): los DATOS de lo que genera el estudio. Los vídeos y archivos pesados no van aquí
-- (pesan gigas): van a Google Drive. Cada fila tiene su dueño (`dueno`) para que, cuando Studio 4 se venda, cada
-- cliente vea solo lo suyo (RLS: seguridad por fila activada en todas las tablas desde el principio).

create table if not exists canales (
  id text primary key,
  dueno uuid not null default auth.uid() references auth.users (id) on delete cascade,
  nombre text not null,
  nicho text, tono text, publico text, voz text,
  redes jsonb not null default '{}'::jsonb,
  fuentes text[] not null default '{}',
  actualizado timestamptz not null default now()
);

create table if not exists videos (
  id text primary key,                          -- el mismo id del montaje en el PC
  dueno uuid not null default auth.uid() references auth.users (id) on delete cascade,
  canal text references canales (id) on delete set null,
  titulo text not null,
  guion text,
  paso smallint, terminado boolean not null default false,
  textos jsonb,                                 -- títulos, descripción, hashtags, capítulos, revisión del empaque
  drive_carpeta text,                           -- dónde están sus archivos en Google Drive
  creado timestamptz not null default now(),
  actualizado timestamptz not null default now()
);

create table if not exists ideas (
  id text primary key,
  dueno uuid not null default auth.uid() references auth.users (id) on delete cascade,
  canal text references canales (id) on delete cascade,
  titulo text not null, gancho text, angulo text, formato text,
  fuentes text[] not null default '{}',
  estado text not null default 'propuesta',     -- propuesta · guardada · en vídeo · descartada
  creado timestamptz not null default now()
);

create table if not exists tendencias (
  id bigint generated always as identity primary key,
  dueno uuid not null default auth.uid() references auth.users (id) on delete cascade,
  canal text references canales (id) on delete cascade,
  dia date not null, tema text not null, fuerza int, titulares text[] not null default '{}'
);

create index if not exists videos_canal on videos (canal);
create index if not exists ideas_canal on ideas (canal);
create index if not exists tendencias_canal_dia on tendencias (canal, dia);

alter table canales enable row level security;
alter table videos enable row level security;
alter table ideas enable row level security;
alter table tendencias enable row level security;

-- cada usuario, solo lo suyo
create policy "lo suyo" on canales for all using ((select auth.uid()) = dueno) with check ((select auth.uid()) = dueno);
create policy "lo suyo" on videos for all using ((select auth.uid()) = dueno) with check ((select auth.uid()) = dueno);
create policy "lo suyo" on ideas for all using ((select auth.uid()) = dueno) with check ((select auth.uid()) = dueno);
create policy "lo suyo" on tendencias for all using ((select auth.uid()) = dueno) with check ((select auth.uid()) = dueno);
