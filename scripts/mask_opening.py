#use regular expression matching module 're'
import re

# Read in the file
with open('covered_copper.txt', 'r') as file :
  filedata = file.read()

# Replace various strings
filedata = filedata.replace('segment', 'gr_line')
filedata = filedata.replace('.Cu")', '.Mask")')

# Delete the (net XYZ) property of the lines
filedata = re.sub(r'\(net.*\) \(', '(', filedata)

# Optionally adjust line width
widthadjust = 0.1

def modifynum(matchobj):
    num = matchobj.group(0)
    modstr = float(num) + widthadjust
    return f'{modstr}'

matchpatt = '(?<=\(width )\d+(?:\.\d*)?(?=\))'
filedata = re.sub(matchpatt, modifynum, filedata)

# Write the file out again
with open('mask_opening.txt', 'w') as file:
  file.write(filedata)
