-- Rekenblad.app: wordt bij installatie gebouwd met osacompile.
-- __PYTHON__ en __SERVER__ worden dan vervangen door de echte paden.

property pythonPath : "__PYTHON__"
property serverPath : "__SERVER__"

on run
	launchWith({})
end run

-- Bestanden die je opent vanuit de Finder, Mail of de Dock komen hier binnen.
on open theItems
	set paths to {}
	repeat with f in theItems
		set end of paths to POSIX path of f
	end repeat
	launchWith(paths)
end open

-- Klik op het Dock-icoon terwijl Rekenblad al draait: nieuw venster.
on reopen
	launchWith({})
end reopen

on launchWith(paths)
	set cmd to quoted form of pythonPath & " " & quoted form of serverPath & " --open"
	repeat with p in paths
		set cmd to cmd & " " & quoted form of (p as text)
	end repeat
	try
		do shell script cmd
	on error errMsg
		display dialog "Rekenblad kon dit niet openen:" & return & return & errMsg buttons {"OK"} default button "OK" with icon caution with title "Rekenblad"
	end try
end launchWith

-- Is de server gestopt? Dan stopt de app ook.
on idle
	try
		do shell script quoted form of pythonPath & " " & quoted form of serverPath & " --status"
	on error
		quit
	end try
	return 15
end idle

on quit
	try
		do shell script quoted form of pythonPath & " " & quoted form of serverPath & " --stop"
	on error errMsg number errNum
		if errNum is 2 then
			set answer to button returned of (display dialog "Er zijn wijzigingen die nog niet zijn opgeslagen." & return & return & errMsg buttons {"Annuleer", "Stop toch"} default button "Annuleer" with icon caution with title "Rekenblad")
			if answer is "Annuleer" then return
			try
				do shell script quoted form of pythonPath & " " & quoted form of serverPath & " --stop --force"
			end try
		end if
	end try
	continue quit
end quit
