import logging
from multiprocessing import Process, Queue
import re
import os, platform
import collections
import tarfile
import sys
import hashlib
import datetime as dt
import zipfile

try:
  from configparser import ConfigParser
except ImportError:
  from ConfigParser import ConfigParser # ver. < 3.0

MULTIPLIER = 50000000

N_PROCESSES = 2
PROJECTS_BATCH = 20
FILE_projects_list = 'projects-list.txt'
FILE_priority_projects = None
PATH_stats_file_folder = 'files_stats'
PATH_bookkeeping_proj_folder = 'bookkeeping_projs'
PATH_tokens_file_folder = 'files_tokens'
PATH_logs = 'logs'

# Reading Language settings
separators = ''
comment_inline = ''
comment_inline_pattern = comment_inline + '.*?$'
comment_open_tag = ''
comment_close_tag = ''
comment_open_close_pattern = comment_open_tag + '.*?' + comment_close_tag
file_extensions = '.none'

file_count = 0

def read_config():
  global N_PROCESSES, PROJECTS_BATCH, FILE_projects_list, FILE_priority_projects
  global PATH_stats_file_folder, PATH_bookkeeping_proj_folder, PATH_tokens_file_folder, PATH_logs
  global separators, comment_inline, comment_inline_pattern, comment_open_tag, comment_close_tag, comment_open_close_pattern
  global file_extensions
  global init_file_id
  global init_proj_id

  # instantiate
  config = ConfigParser()
  # parse existing file
  try:
    config.read(os.path.join(os.path.dirname(os.path.abspath(__file__)) , 'config.ini'))
  except IOError:
    print('ERROR - Config settings not found. Usage: $python this-script.py config-file.ini')
    sys.exit()

  # Get info from config.ini into global variables
  N_PROCESSES = config.getint('Main', 'N_PROCESSES')
  PROJECTS_BATCH = config.getint('Main', 'PROJECTS_BATCH')
  FILE_projects_list = config.get('Main', 'FILE_projects_list')
  if config.has_option('Main', 'FILE_priority_projects'):
    FILE_priority_projects = config.get('Main', 'FILE_priority_projects')
  PATH_stats_file_folder = config.get('Folders/Files', 'PATH_stats_file_folder')
  PATH_bookkeeping_proj_folder = config.get('Folders/Files', 'PATH_bookkeeping_proj_folder')
  PATH_tokens_file_folder = config.get('Folders/Files', 'PATH_tokens_file_folder')
  PATH_logs = config.get('Folders/Files', 'PATH_logs')

  # Reading Language settings
  separators = config.get('Language', 'separators').strip('"').split(' ')
  comment_inline = re.escape(config.get('Language', 'comment_inline'))
  comment_inline_pattern = comment_inline + '.*?$'
  comment_open_tag = re.escape(config.get('Language', 'comment_open_tag'))
  comment_close_tag = re.escape(config.get('Language', 'comment_close_tag'))
  comment_open_close_pattern = comment_open_tag + '.*?' + comment_close_tag
  file_extensions = config.get('Language', 'File_extensions').split(' ')
  # Reading config settings
  init_file_id = config.getint('Config', 'init_file_id')
  init_proj_id = config.getint('Config', 'init_proj_id')

def tokenize_files(file_string, comment_inline_pattern, comment_open_close_pattern, separators):
  final_stats  = final_tokens = file_hash = lines = LOC = SLOC = 'ERROR'
  h_time = dt.datetime.now()
  m = hashlib.md5()
  m.update(file_string)
  file_hash = m.hexdigest()
  hash_time = (dt.datetime.now() - h_time).microseconds
  lines = file_string.count('\n')
  if not file_string.endswith('\n'):
    lines += 1
  file_string = "".join([s for s in file_string.splitlines(True) if s.strip()])

  LOC = file_string.count('\n')
  if not file_string.endswith('\n'):
    LOC += 1

  re_time = dt.datetime.now()
  # Remove tagged comments
  file_string = re.sub(comment_open_close_pattern, '', file_string, flags=re.DOTALL)
  # Remove end of line comments
  file_string = re.sub(comment_inline_pattern, '', file_string, flags=re.MULTILINE)
  re_time = (dt.datetime.now() - re_time).microseconds

  file_string = "".join([s for s in file_string.splitlines(True) if s.strip()]).strip()
  SLOC = file_string.count('\n')
  if file_string != '' and not file_string.endswith('\n'):
    SLOC += 1
  final_stats = (file_hash,lines,LOC,SLOC)
  # Rather a copy of the file string here for tokenization
  file_string_for_tokenization = file_string.decode('utf-8')
  #Transform separators into spaces (remove them)
  s_time = dt.datetime.now()
  for x in separators:
    file_string_for_tokenization = file_string_for_tokenization.replace(x,' ')
  s_time = (dt.datetime.now() - s_time).microseconds
  ##Create a list of tokens
  file_string_for_tokenization = file_string_for_tokenization.split()
  ## Total number of tokens
  tokens_count_total = len(file_string_for_tokenization)
  ##Count occurrences
  file_string_for_tokenization = collections.Counter(file_string_for_tokenization)
  ##Converting Counter to dict because according to StackOverflow is better
  file_string_for_tokenization = dict(file_string_for_tokenization)
  ## Unique number of tokens
  tokens_count_unique = len(file_string_for_tokenization)
  t_time = dt.datetime.now()
  #SourcererCC formatting
  tokens = ','.join(['{}@@::@@{}'.format(k.encode('utf-8'), v) for k, v in file_string_for_tokenization.iteritems()])
  t_time = (dt.datetime.now() - t_time).microseconds
  # MD5
  h_time = dt.datetime.now()
  m = hashlib.md5()
  m.update(tokens)
  hash_time += (dt.datetime.now() - h_time).microseconds
  final_tokens = (tokens_count_total, tokens_count_unique, m.hexdigest(), '@#@' + tokens)
  return (final_stats, final_tokens, [s_time, t_time, hash_time, re_time])

def process_file_contents(file_string, proj_id, file_id, container_path, file_path, file_bytes, proj_url, FILE_tokens_file, FILE_stats_file, logging):
  global file_count

  file_count += 1
  (final_stats, final_tokens, file_parsing_times) = tokenize_files(file_string, comment_inline_pattern, comment_open_close_pattern, separators)
  (file_hash,lines,LOC,SLOC) = final_stats
  (tokens_count_total,tokens_count_unique,token_hash,tokens) = final_tokens
  file_url = proj_url + '/' + file_path[7:].replace(' ', '%20')
  file_path = os.path.join(container_path, file_path)
  ww_time = dt.datetime.now()
  FILE_stats_file.write(','.join([proj_id, str(file_id), '\"' + file_path + '\"', '\"' + file_url + '\"', '\"' + file_hash + '\"', file_bytes, str(lines), str(LOC), str(SLOC)]) + '\n')
  w_time = (dt.datetime.now() - ww_time).microseconds
  ww_time = dt.datetime.now()
  FILE_tokens_file.write(','.join([proj_id, str(file_id), str(tokens_count_total), str(tokens_count_unique), token_hash + tokens]) + '\n')
  w_time += (dt.datetime.now() - ww_time).microseconds
  return file_parsing_times + [w_time] # [s_time, t_time, w_time, hash_time, re_time]

def process_regular_folder(args, folder_path, files):
  process_num, proj_id, _, proj_url, base_file_id, FILE_tokens_file, _, FILE_stats_file, logging, times = args
  all_files = files
  # Filter them by the correct extension
  aux = []
  for extension in file_extensions:
    aux.extend([x for x in all_files if x.endswith(extension)])
  all_files = aux
  # This is very strange, but I did find some paths with newlines,
  # so I am simply eliminates them
  all_files = [x for x in all_files if '\n' not in x]

  for file_path in all_files:
    file_id = process_num * MULTIPLIER + base_file_id + file_count
    print("<%s, %s, %s>" % (file_id, folder_path, file_path))
    file_path = os.path.join(folder_path, file_path)

    with open(file_path) as f:
      f_time = dt.datetime.now()
      file_string = f.read()
      f_time = (dt.datetime.now() - f_time).microseconds
      times_c = process_file_contents(file_string, proj_id, file_id, "", file_path, str(os.path.getsize(file_path)), proj_url, FILE_tokens_file, FILE_stats_file, logging)
      times[0] += f_time
      times[1] += times_c[0]
      times[2] += times_c[1]
      times[3] += times_c[4]
      times[4] += times_c[2]
      times[5] += times_c[3]

def process_tgz_ball(process_num, tar_file, proj_id, proj_path, proj_url, base_file_id, FILE_tokens_file, FILE_bookkeeping_proj, FILE_stats_file, logging):
  zip_time = file_time = string_time = tokens_time = hash_time = write_time = regex_time = 0
  logging.info('Attempting to process_tgz_ball ' + tar_file)
  try:
    with tarfile.open(tar_file, 'r|*') as my_tar_file:
      for f in my_tar_file:
        if not f.isfile():
          continue
        # Filter by the correct extension
        if not os.path.splitext(f.name)[1] in file_extensions:
          continue
        # This is very strange, but I did find some paths with newlines,
        # so I am simply ignoring them
        if '\n' in f.name:
          continue

        file_id = process_num * MULTIPLIER + base_file_id + file_count
        file_bytes = str(f.size)
        z_time = dt.datetime.now()
        try:
          myfile = my_tar_file.extractfile(f)
        except:
          logging.warning('Unable to open file (1) <' + proj_id + ',' + str(file_id) + ',' + os.path.join(tar_file, f.name) + '> (process ' + str(process_num) + ')')
          break
        zip_time += (dt.datetime.now() - z_time).microseconds

        if myfile is None:
          logging.warning('Unable to open file (2) <' + proj_id + ',' + str(file_id) + ',' + os.path.join(tar_file, f.name) + '> (process ' + str(process_num) + ')')
          break

        f_time = dt.datetime.now()
        file_string = myfile.read()
        file_time += (dt.datetime.now() - f_time).microseconds

        file_path = f.name
        times = process_file_contents(file_string, proj_id, file_id, tar_file, file_path, file_bytes, proj_url, FILE_tokens_file, FILE_stats_file, logging)
        string_time += times[0]
        tokens_time += times[1]
        write_time  += times[4]
        hash_time   += times[2]
        regex_time  += times[3]
  except Exception as e:
    logging.warning('Unable to open tar on <' + proj_id + ',' + proj_path + '> (process ' + str(process_num) + ')')
    logging.warning(e)
    return
  return (zip_time, file_time, string_time, tokens_time, write_time, hash_time, regex_time)

def process_zip_ball(process_num, zip_file, proj_id, proj_path, proj_url, base_file_id, FILE_tokens_file, FILE_bookkeeping_proj, FILE_stats_file, logging):
  zip_time = file_time = string_time = tokens_time = hash_time = write_time = regex_time = 0
  logging.info('Attempting to process_zip_ball ' + zip_file)
  try:
    with zipfile.ZipFile(proj_path,'r') as my_file:
      for file in my_file.infolist():
        if not os.path.splitext(file.filename)[1] in file_extensions:
          continue
        # This is very strange, but I did find some paths with newlines,
        # so I am simply ignoring them
        if '\n' in file.filename:
          continue

        file_id = process_num * MULTIPLIER + base_file_id + file_count
        file_bytes = str(file.file_size)
        z_time = dt.datetime.now()
        try:
          my_zip_file = my_file.open(file.filename, 'r')
        except:
          logging.warning('Unable to open file (1) <' + os.path.join(proj_path, file.filename) + '> (process ' + str(process_num) + ')')
          break
        zip_time += (dt.datetime.now() - z_time).microseconds

        if my_zip_file is None:
          logging.warning('Unable to open file (2) <' + os.path.join(proj_path, file.filename) + '> (process ' + str(process_num) + ')')
          break

        f_time = dt.datetime.now()
        file_string = my_zip_file.read()
        file_time += (dt.datetime.now() - f_time).microseconds

        file_path = file.filename
        times = process_file_contents(file_string, proj_id, file_id, zip_file, file_path, file_bytes, proj_url, FILE_tokens_file, FILE_stats_file, logging)
        string_time += times[0]
        tokens_time += times[1]
        write_time  += times[4]
        hash_time   += times[2]
        regex_time  += times[3]
  except Exception as e:
    logging.warning('Unable to open zip on <' + proj_path + '> (process ' + str(process_num) + ')')
    logging.warning(e)
    return
  logging.info('Successfully ran process_zip_ball ' + zip_file)
  return (zip_time, file_time, string_time, tokens_time, write_time, hash_time, regex_time)

def process_one_project(process_num, proj_id, proj_path, base_file_id, FILE_tokens_file, FILE_bookkeeping_proj, FILE_stats_file, logging, project_format):
  p_start = dt.datetime.now()
  logging.info('Starting ' + project_format + ' project <' + proj_id + ',' + proj_path + '> (process ' + str(process_num) + ')')
  if not os.path.isfile(proj_path):
      logging.warning('Unable to open project <'+proj_id+','+proj_path+'> (process '+str(process_num)+')')
      return

  if project_format == 'leidos':
    proj_url = 'None'
    # Search for tar files with _code in them
    tar_files = [os.path.join(proj_path, f) for f in os.listdir(proj_path) if os.path.isfile(os.path.join(proj_path, f))]
    tar_files = [f for f in tar_files if '_code' in f]
    if(len(tar_files) != 1):
      logging.warning('Tar not found on <'+proj_id+','+proj_path+'> (process '+str(process_num)+')')
      times = [0,0,0,0,0,0,0]
      os.path.walk(proj_path, process_regular_folder, (process_num, proj_id, proj_path, proj_url, base_file_id, FILE_tokens_file, FILE_bookkeeping_proj, FILE_stats_file, logging, times))
    else:
      tar_file = tar_files[0]
      times = process_tgz_ball(process_num, tar_file, proj_id, proj_path, proj_url, base_file_id, FILE_tokens_file, FILE_bookkeeping_proj, FILE_stats_file, logging)
  elif project_format == 'zip':
    proj_url = 'NULL'
    zip_file = proj_path
    times = process_zip_ball(process_num, zip_file, proj_id, proj_path, proj_url, base_file_id, FILE_tokens_file, FILE_bookkeeping_proj, FILE_stats_file, logging)
  zip_time, file_time, string_time, tokens_time, write_time, hash_time, regex_time = (times if times is not None else (-1, -1, -1, -1, -1, -1, -1))

  FILE_bookkeeping_proj.write(proj_id + ',\"' + proj_path + '\",\"' + proj_url + '\"\n')
  p_elapsed = dt.datetime.now() - p_start
  logging.info('Project finished <%s,%s> (process %s)', proj_id, proj_path, process_num)
  logging.info(' (%s): Total: %s ms', process_num,  p_elapsed)
  logging.info('     Zip: %s', zip_time)
  logging.info('     Read: %s', file_time)
  logging.info('     Separators: %s ms', string_time)
  logging.info('     Tokens: %s ms', tokens_time)
  logging.info('     Write: %s ms', write_time)
  logging.info('     Hash: %s', hash_time)
  logging.info('     regex: %s', regex_time)

def process_projects(process_num, list_projects, base_file_id, global_queue, project_format):
    if platform.system() == 'Windows':
        read_config()

    # Logging code
    FORMAT = '[%(levelname)s] (%(threadName)s) %(message)s'
    logging.basicConfig(level = logging.DEBUG, format = FORMAT)
    file_handler = logging.FileHandler(os.path.join(PATH_logs, 'LOG-' + str(process_num) + '.log'))
    file_handler.setFormatter(logging.Formatter(FORMAT))
    logging.getLogger().addHandler(file_handler)

    FILE_files_stats_file = os.path.join(PATH_stats_file_folder, 'files-stats-' + str(process_num) + '.stats')
    FILE_bookkeeping_proj_name = os.path.join(PATH_bookkeeping_proj_folder, 'bookkeeping-proj-' + str(process_num) + '.projs')
    FILE_files_tokens_file = os.path.join(PATH_tokens_file_folder, 'files-tokens-' + str(process_num) + '.tokens')

    global file_count
    file_count = 0
    with open(FILE_files_tokens_file, 'a+') as FILE_tokens, open(FILE_bookkeeping_proj_name, 'a+') as FILE_bookkeeping, open(FILE_files_stats_file, 'a+') as FILE_stats:
        logging.info("Process %s starting", process_num)
        p_start = dt.datetime.now()
        for proj_id, proj_path in list_projects:
            process_one_project(process_num, str(proj_id), proj_path, base_file_id, FILE_tokens, FILE_bookkeeping, FILE_stats, logging, project_format)

    p_elapsed = (dt.datetime.now() - p_start).seconds
    logging.info('Process %s finished. %s files in %ss.', process_num, file_count, p_elapsed)

    # Let parent know
    global_queue.put((process_num, file_count))
    sys.exit(0)

def start_child(processes, global_queue, proj_paths, batch, project_format):
  # This is a blocking get. If the queue is empty, it waits
  pid, n_files_processed = global_queue.get()
  # OK, one of the processes finished. Let's get its data and kill it
  kill_child(processes, pid, n_files_processed)

  # Get a new batch of project paths ready
  paths_batch = proj_paths[:batch]
  del proj_paths[:batch]

  print("Starting new process %s" % (pid))
  p = Process(name = 'Process ' + str(pid), target = process_projects, args = (pid, paths_batch, processes[pid][1], global_queue, project_format))
  processes[pid][0] = p
  p.start()

def kill_child(processes, pid, n_files_processed):
  global file_count
  file_count += n_files_processed
  if processes[pid][0] != None:
    processes[pid][0] = None
    processes[pid][1] += n_files_processed
    print("Process %s finished, %s files processed (%s). Current total: %s" % (pid, n_files_processed, processes[pid][1], file_count))

def active_process_count(processes):
  return len(filter(lambda p : p[0] != None, processes))

if __name__ == '__main__':
  global project_format
  project_format = sys.argv[1]

  if project_format not in ['zip','leidos']:
    print("ERROR - Please insert archive format, 'zip', 'leidos'!")
    sys.exit()

  read_config()
  p_start = dt.datetime.now()

  prio_proj_paths = []
  if FILE_priority_projects != None:
    with open(FILE_priority_projects) as f:
      for line in f:
        line_split = line.strip('\n')
        prio_proj_paths.append(line_split)
    prio_proj_paths = zip(range(init_proj_id, len(prio_proj_paths)+init_proj_id), prio_proj_paths)

  proj_paths = []
  print('\'',project_format,'\'','format')
  if project_format == 'leidos':
    with open(FILE_projects_list) as f:
      for line in f:
        prio = False
        line_split = line.strip('\n')
        for p in prio_proj_paths:
          if p[1][0] == line_split:
            prio = True
            print "Project %s is in priority list" % line_split
        if not prio:
          proj_paths.append(line_split)
  elif project_format == 'zip':
    with open(FILE_projects_list) as f:
      for line in f:
        proj_paths.append(line.strip("\n"))
  proj_paths = zip(range(1, len(proj_paths)+1), proj_paths)

  if os.path.exists(PATH_stats_file_folder) or os.path.exists(PATH_bookkeeping_proj_folder) or os.path.exists(PATH_tokens_file_folder) or os.path.exists(PATH_logs):
    missing_files = filter(os.path.exists, [PATH_stats_file_folder, PATH_bookkeeping_proj_folder, PATH_tokens_file_folder, PATH_logs])
    print('ERROR - Folder [' + '] or ['.join(missing_files) + '] already exists!')
    sys.exit(1)
  else:
    os.makedirs(PATH_stats_file_folder)
    os.makedirs(PATH_bookkeeping_proj_folder)
    os.makedirs(PATH_tokens_file_folder)
    os.makedirs(PATH_logs)

  #Split list of projects into N_PROCESSES lists
  #proj_paths_list = [ proj_paths[i::N_PROCESSES] for i in xrange(N_PROCESSES) ]

  # Multiprocessing with N_PROCESSES
  # [process, file_count]
  processes = [[None, init_file_id] for i in xrange(N_PROCESSES)]
  # Multiprocessing shared variable instance for recording file_id
  #file_id_global_var = Value('i', 1)
  # The queue for processes to communicate back to the parent (this process)
  # Initialize it with N_PROCESSES number of (process_id, n_files_processed)
  global_queue = Queue()
  for i in xrange(N_PROCESSES):
    global_queue.put((i, 0))

  # Start the priority projects
  print("*** Starting priority projects...")
  while len(prio_proj_paths) > 0:
    start_child(processes, global_queue, prio_proj_paths, 1, project_format)

  # Start all other projects
  print("*** Starting regular projects...")
  while len(proj_paths) > 0:
    start_child(processes, global_queue, proj_paths, PROJECTS_BATCH, project_format)

  print("*** No more projects to process. Waiting for children to finish...")
  while active_process_count(processes) > 0:
    pid, n_files_processed = global_queue.get()
    kill_child(processes, pid, n_files_processed)

  p_elapsed = dt.datetime.now() - p_start
  print("*** All done. %s files in %s" % (file_count, p_elapsed))
