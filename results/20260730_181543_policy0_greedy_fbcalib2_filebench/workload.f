set $dir=/home/hjyoo/nvme_mount
set $filesize=2g
set $iosize=4k
set $nthreads=4

define file name=gcfile,path=$dir,size=$filesize,prealloc,reuse

define process name=filewriter,instances=1
{
  thread name=filewriterthread,memsize=10m,instances=$nthreads
  {
    flowop write name=write-file,filename=gcfile,random,iosize=$iosize
    flowop fsync name=sync-file,filename=gcfile
  }
}

run 120
