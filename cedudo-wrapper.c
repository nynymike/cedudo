/*
 * cedudo-wrapper.c
 * 
 * Setuid wrapper for cedudo.py
 * 
 * Compiled binaries can use setuid, but interpreted scripts cannot on most
 * modern Linux systems. This wrapper is a compiled binary that becomes setuid
 * root and then executes the Python script with elevated privileges.
 * 
 * Compile and install:
 *   gcc -o cedudo-wrapper cedudo-wrapper.c
 *   sudo cp cedudo-wrapper /opt/cedudo/cedudo
 *   sudo chown root:root /opt/cedudo/cedudo
 *   sudo chmod 4755 /opt/cedudo/cedudo
 *   sudo ln -sf /opt/cedudo/cedudo /usr/local/bin/cedudo
 */

#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>

#define PYTHON_PATH "/opt/cedudo/venv/bin/python3"
#define SCRIPT_PATH "/opt/cedudo/cedudo.py"

int main(int argc, char *argv[]) {
    /* Build argument array for execv:
     * python_args[0] = python interpreter path
     * python_args[1] = script path  
     * python_args[2..argc] = original arguments from user
     * python_args[argc+1] = NULL terminator
     */
    char *python_args[argc + 2];
    
    python_args[0] = PYTHON_PATH;
    python_args[1] = SCRIPT_PATH;
    
    /* Copy user arguments (skipping argv[0] which is the wrapper name) */
    for (int i = 1; i < argc; i++) {
        python_args[i + 1] = argv[i];
    }
    
    /* NULL-terminate the array */
    python_args[argc + 1] = NULL;
    
    /* Execute Python with the script
     * This replaces the current process with Python.
     * The setuid bit on this binary means Python runs as root.
     * Python then executes cedudo.py with root effective UID.
     * cedudo.py can then read the real UID to identify the original user.
     */
    execv(python_args[0], python_args);
    
    /* If we get here, execv failed */
    perror("cedudo-wrapper: execv failed");
    return 1;
}
