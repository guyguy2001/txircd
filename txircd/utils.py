import re

def _enum(**enums):
    return type('Enum', (), enums)

ModeType = _enum(List=0, ParamOnUnset=1, Param=2, NoParam=3, Status=4)

ipv4MappedAddr = re.compile("::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})")
def unmapIPv4(ip):
    mapped = ipv4MappedAddr.match(ip)
    if mapped:
        return mapped.group(1)
    return ip

def unescapeEndpointDescription(desc):
    result = []
    escape = []
    depth = 0
    desc = iter(desc)
    for char in desc:
        if char == "\\":
            try:
                char = desc.next()
            except StopIteration:
                raise ValueError ("Endpoint description not valid: escaped end of string")
            if char not in "{}":
                char = "\\{}".format(char)
            if depth == 0:
                result.extend(char)
            else:
                escape.extend(char)
        elif char == "{":
            if depth > 0:
                escape.append("{")
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise ValueError ("Endpoint description not valid: mismatched end brace")
            if depth == 0:
                result.extend(unescapeEndpointDescription("".join(escape)).replace("\\", "\\\\").replace(":", "\\:").replace("=", "\\="))
            else:
                escape.append("}")
        else:
            if depth == 0:
                result.append(char)
            else:
                escape.append(char)
    if depth != 0:
        raise ValueError ("Endpoint description not valid: mismatched opening brace")
    return "".join(result)