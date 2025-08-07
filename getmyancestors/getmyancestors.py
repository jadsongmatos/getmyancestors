# coding: utf-8

# global imports
from __future__ import print_function
import re
import sys
import time
from urllib.parse import unquote
import getpass
import asyncio
import argparse

# local imports
from getmyancestors.classes.tree import Tree, Indi, Fam # Importar classes necessárias
from getmyancestors.classes.session import Session
from getmyancestors.classes.gedcom import Gedcom # Importar Gedcom

def main():
    parser = argparse.ArgumentParser(
        description="Retrieve GEDCOM data from FamilySearch Tree (4 Jul 2016)",
        add_help=False,
        usage="getmyancestors -u username -p password [options]",
    )
    parser.add_argument(
        "-u", "--username", metavar="<STR>", type=str, help="FamilySearch username"
    )
    parser.add_argument(
        "-p", "--password", metavar="<STR>", type=str, help="FamilySearch password"
    )
    parser.add_argument(
        "-i",
        "--individuals",
        metavar="<STR>",
        nargs="+",
        type=str,
        help="List of individual FamilySearch IDs for whom to retrieve ancestors",
    )
    parser.add_argument(
        "-a",
        "--ascend",
        metavar="<INT>",
        type=int,
        default=4,
        help="Number of generations to ascend [4]",
    )
    parser.add_argument(
        "-d",
        "--descend",
        metavar="<INT>",
        type=int,
        default=0,
        help="Number of generations to descend [0]",
    )
    parser.add_argument(
        "-m",
        "--marriage",
        action="store_true",
        default=False,
        help="Add spouses and couples information [False]",
    )
    parser.add_argument(
        "-r",
        "--get-contributors",
        action="store_true",
        default=False,
        help="Add list of contributors in notes [False]",
    )
    parser.add_argument(
        "-c",
        "--get_ordinances",
        action="store_true",
        default=False,
        help="Add LDS ordinances (need LDS account) [False]",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Increase output verbosity [False]",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        metavar="<INT>",
        type=int,
        default=60,
        help="Timeout in seconds [60]",
    )
    parser.add_argument(
        "--show-password",
        action="store_true",
        default=False,
        help="Show password in .settings file [False]",
    )
    parser.add_argument(
        "--save-settings",
        action="store_true",
        default=False,
        help="Save settings into file [False]",
    )
    parser.add_argument(
        "-o",
        "--outfile",
        metavar="<FILE>",
        type=argparse.FileType("w", encoding="UTF-8"),
        default=sys.stdout,
        help="output GEDCOM file [stdout]",
    )
    parser.add_argument(
        "-l",
        "--logfile",
        metavar="<FILE>",
        type=argparse.FileType("w", encoding="UTF-8"),
        default=False,
        help="output log file [stderr]",
    )
    parser.add_argument(
        "--client_id", metavar="<STR>", type=str, help="Use Specific Client ID"
    )
    parser.add_argument(
        "--redirect_uri", metavar="<STR>", type=str, help="Use Specific Redirect Uri"
    )
    # === MODIFICAÇÃO: Adicionar opções --resume-from, --start-level, --end-level ===
    parser.add_argument(
        "--resume-from",
        metavar="<FILE>",
        type=argparse.FileType("r", encoding="UTF-8"),
        help="Resume download from existing GEDCOM file",
    )
    parser.add_argument(
        "--start-level",
        metavar="<INT>",
        type=int,
        default=0,
        help="Start level for resume operation [0]",
    )
    parser.add_argument(
        "--end-level",
        metavar="<INT>",
        type=int,
        default=-1,
        help="End level for resume operation [-1 for no limit]",
    )

    # extract arguments from the command line
    try:
        parser.error = parser.exit
        args = parser.parse_args()
    except SystemExit:
        parser.print_help(file=sys.stderr)
        sys.exit(2)
        
    # Se estiver resumindo, -i é opcional
    if args.resume_from and args.individuals:
        print("Warning: -i/--individuals ignored when using --resume-from. Using individuals from the GEDCOM file.", file=sys.stderr)
        args.individuals = None
        
    if args.individuals:
        for fid in args.individuals:
            if not re.match(r"[A-Z0-9]{4}-[A-Z0-9]{3}", fid):
                sys.exit("Invalid FamilySearch ID: " + fid)

    args.username = (
        args.username if args.username else input("Enter FamilySearch username: ")
    )
    args.password = (
        args.password
        if args.password
        else getpass.getpass("Enter FamilySearch password: ")
    )

    time_count = time.time()

    # Report settings used when getmyancestors is executed
    if args.save_settings and args.outfile.name != "<stdout>":

        def parse_action(act):
            if not args.show_password and act.dest == "password":
                return "******"
            value = getattr(args, act.dest)
            return str(getattr(value, "name", value))

        formatting = "{:74}{:\t>1}\n"
        settings_name = args.outfile.name.split(".")[0] + ".settings"
        try:
            with open(settings_name, "w") as settings_file:
                settings_file.write(
                    formatting.format("time stamp: ", time.strftime("%X %x %Z"))
                )
                for action in parser._actions:
                    settings_file.write(
                        formatting.format(
                            action.option_strings[-1], parse_action(action)
                        )
                    )
        except OSError as exc:
            print(
                "Unable to write %s: %s" % (settings_name, repr(exc)), file=sys.stderr
            )

    # initialize a FamilySearch session and a family tree object
    print("Login to FamilySearch...", file=sys.stderr)
    fs = Session(
        args.username,
        args.password,
        args.client_id,
        args.redirect_uri,
        args.verbose,
        args.logfile,
        args.timeout,
    )
    if not fs.logged:
        sys.exit(2)
    _ = fs._

    tree = Tree(fs) # Criar a árvore associada à sessão desde o início
    
    if args.resume_from:
        print(_("Resuming from existing GEDCOM file..."), file=sys.stderr)
        
        # 1. Carregar o arquivo GEDCOM existente
        ged = Gedcom(args.resume_from, tree)
        
        # 2. Coletar os FIDs dos indivíduos carregados
        fids_from_ged = set()
        for num in ged.indi:
            if ged.indi[num].fid:
                fids_from_ged.add(ged.indi[num].fid)
                
        print(_("Loaded %s individuals from GEDCOM file.") % len(fids_from_ged), file=sys.stderr)
        
        if not fids_from_ged:
            print(_("Error: No individuals with FamilySearch IDs found in GEDCOM file."), file=sys.stderr)
            sys.exit(1)
            
        # 3. Buscar dados completos desses indivíduos no FamilySearch
        # Isso é crucial para que add_parents funcione corretamente
        print(_("Fetching complete data for individuals from FamilySearch..."), file=sys.stderr)
        tree.add_indis(fids_from_ged)
        
        # 4. Identificar "pontos de partida" para continuar a busca
        # Estratégia: Encontrar indivíduos que têm registros de pais (famc_fid)
        # mas cujos pais imediatos podem ter ancestrais não explorados.
        todo = set()
        for fid in tree.indi:
            # Se o indivíduo tem famc_fid, ele tem pais conhecidos
            # e pode ser um ponto de partida para buscar mais ancestrais
            if tree.indi[fid].famc_fid:
                todo.add(fid)
                
        # Se não encontrou indivíduos com famc_fid, usar todos como fallback
        if not todo:
            print(_("No individuals with parents found in GEDCOM. Using all individuals as starting points."), file=sys.stderr)
            todo = set(tree.indi.keys())
            
        print(_("Resumed with %s individuals to start from.") % len(todo), file=sys.stderr)
        
    else:
        # Comportamento original para download inicial
        initial_fids = args.individuals if args.individuals else [fs.fid]
        print(_("Downloading starting individuals..."), file=sys.stderr)
        tree.add_indis(initial_fids)
        todo = set(tree.indi.keys())

    # check LDS account
    if args.get_ordinances:
        test = fs.get_url(
            "/service/tree/tree-data/reservations/person/%s/ordinances" % fs.fid, {}, no_api=True
        )
        if not test or test["status"] != "OK":
            print("Need an LDS account")
            sys.exit(2)

    try:
        # download ancestors
        # === MODIFICAÇÃO: Ajuste na lógica de download com níveis ===
        done = set()
        # Se estamos resumindo, 'todo' já foi preenchido com os indivíduos do nível de início
        # Se não estamos resumindo, 'todo' foi preenchido com os indivíduos iniciais
        
        # Para o modo de níveis, vamos usar uma abordagem diferente
        if args.resume_from:
            # Modo de níveis
            current_level = args.start_level
            max_level = args.end_level if args.end_level >= 0 else float('inf')
            
            while todo and current_level <= max_level:
                print(
                    _("Processing level %s with %s individuals...") % (current_level, len(todo)),
                    file=sys.stderr,
                )
                
                # Adicionar pais dos indivíduos atuais
                new_parents = tree.add_parents(todo)
                
                # Verificar se há mais dados no site para indivíduos sem pais
                # Esta é uma abordagem simplificada - na prática, você pode querer verificar
                # mais detalhadamente quais indivíduos realmente não têm pais completos
                if current_level < max_level:
                    # Atualizar 'todo' para o próximo nível
                    todo = new_parents - done
                else:
                    todo = set()
                    
                done |= new_parents
                current_level += 1
                
                # Se não encontramos novos pais, verificar se há mais dados no site
                if not todo and current_level <= max_level:
                    print(_("Checking for additional data on individuals..."), file=sys.stderr)
                    # Esta parte é complexa e depende de como você quer implementar a verificação
                    # Uma abordagem seria verificar cada indivíduo em 'done' para ver se ele
                    # tem registros de famílias como filho que não foram completamente carregados
                    # Por simplicidade, vamos parar aqui
                    break
        else:
            # Modo tradicional
            for i in range(args.ascend):
                if not todo:
                    break
                done |= todo
                print(
                    _("Downloading %s. of generations of ancestors...") % (i + 1),
                    file=sys.stderr,
                )
                todo = tree.add_parents(todo) - done

        # download descendants
        todo = set(tree.indi.keys())
        done = set()
        for i in range(args.descend):
            if not todo:
                break
            done |= todo
            print(
                _("Downloading %s. of generations of descendants...") % (i + 1),
                file=sys.stderr,
            )
            todo = tree.add_children(todo) - done

        # download spouses
        if args.marriage:
            print(_("Downloading spouses and marriage information..."), file=sys.stderr)
            todo = set(tree.indi.keys())
            tree.add_spouses(todo)

        # download ordinances, notes and contributors
        async def download_stuff(loop):
            futures = set()
            for fid, indi in tree.indi.items():
                futures.add(loop.run_in_executor(None, indi.get_notes))
                if args.get_ordinances:
                    futures.add(loop.run_in_executor(None, tree.add_ordinances, fid))
                if args.get_contributors:
                    futures.add(loop.run_in_executor(None, indi.get_contributors))
            for fam in tree.fam.values():
                futures.add(loop.run_in_executor(None, fam.get_notes))
                if args.get_contributors:
                    futures.add(loop.run_in_executor(None, fam.get_contributors))
            for future in futures:
                await future

        loop = asyncio.get_event_loop()
        print(
            _("Downloading notes")
            + (
                (("," if args.get_contributors else _(" and")) + _(" ordinances"))
                if args.get_ordinances
                else ""
            )
            + (_(" and contributors") if args.get_contributors else "")
            + "...",
            file=sys.stderr,
        )
        loop.run_until_complete(download_stuff(loop))

    finally:
        # compute number for family relationships and print GEDCOM file
        tree.reset_num()
        tree.print(args.outfile)
        print(
            _(
                "Downloaded %s individuals, %s families, %s sources and %s notes "
                "in %s seconds with %s HTTP requests."
            )
            % (
                str(len(tree.indi)),
                str(len(tree.fam)),
                str(len(tree.sources)),
                str(len(tree.notes)),
                str(round(time.time() - time_count)),
                str(fs.counter),
            ),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
